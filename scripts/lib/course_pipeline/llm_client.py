"""LLM 适配层：三个后端共用一条「解析 → schema 校验」路径（spec `D2` / GC8 / GC9 / GC12）。

后端语义（GC8：三者不是三个生产后端，而是同一 schema 下的三种执行体）：

- `cli`：生产路径。OpenAI 兼容 `POST {ZIKAO_LLM_BASE_URL}/chat/completions`（`urllib.request`，无第三方 SDK），
  `response_format={"type": "json_object"}`，超时 120s，失败重试 2 次（指数退避 1s / 2s），
  响应先 `json.loads` 再按提示词自带的 JSON schema 校验；3 次尝试仍不合法 → `RuntimeError`
  （**不放宽 schema、不填占位文本**，Task 4 STOP (a)）。
- `agent`：无 key 环境的第二执行体。把「提示词 + 输入 JSON」写成
  `sources/jiangsu/courses/<code>/.agent-task/<prompt_id>-<n>.json`，等 harness agent 回填同目录
  `<...>.result.json`；缺回填结果 → `AgentTasksPendingError` 点名全部缺失文件（**不伪造**）。
  `.agent-task/` 是运行态，不入 git。
- `replay`：CI 离线回归。按 `payload` 稳定哈希读
  `tests/fixtures/course_pipeline/llm/<prompt_id>.<prompt_version>.json`；缺文件或缺条目 → `RuntimeError`
  （**不回落模板**）。

`generator_metadata()` 返回该次调用的来源（`backend` / `model` / `generated_at`）：`cli` / `agent` 取当天日期，
`replay` 回放**录制时**的来源 —— 因此 `--backend replay` 复跑与首次产物逐字段一致（AC9 幂等口径）。

密钥与端点只从环境变量读（`ZIKAO_LLM_BASE_URL` / `ZIKAO_LLM_API_KEY` / `ZIKAO_LLM_MODEL`），
报错文案只允许出现**变量名**，不得出现其值（GC9）。测试不联网：`cli` 路径由 monkeypatch
`urllib.request.urlopen` 注入传输。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date
from hashlib import sha256
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "course_pipeline" / "llm"
# `complete_json()` 没有 root 参数（签名与 plan § Target-state module map 逐字一致），
# 因此 `agent` 后端的 `.agent-task` 根由仓根推导；测试用 monkeypatch 指向 tmp_path。
COURSES_DIR = REPO_ROOT / "sources" / "jiangsu" / "courses"


def set_repo_root(root: Path) -> None:
    """把 fixture / 提示词 / `.agent-task` 三个根重定向到 `root`（QC3-007 / C2-010）。

    默认由 `__file__` 推导，于是从**副本仓**跑 `build` 时仍会读到真实仓的 fixture —— 失败关闭测试
    可能因为「真实仓恰好可用」而通过，与副本仓的真实状态无关。调用方可显式重定向，
    使入口路径的测试真正作用于被测试的那棵树。
    """
    global REPO_ROOT, FIXTURES_DIR, COURSES_DIR
    REPO_ROOT = root
    FIXTURES_DIR = root / "tests" / "fixtures" / "course_pipeline" / "llm"
    COURSES_DIR = root / "sources" / "jiangsu" / "courses"

BACKENDS = ("cli", "agent", "replay")
AGENT_TASK_DIRNAME = ".agent-task"
DEFAULT_AGENT_MODEL = "harness-agent"
HTTP_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 1
SCHEMA_FENCE_RE = re.compile(r"```json schema\n(?P<schema>.*?)\n```", re.S)
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.S)
COURSE_SCOPE_LINE_RE = re.compile(r"^course_scope:[ \t]*(?P<value>\[.*\])[ \t]*$", re.M)
BUNDLE_NAME_RE_TEMPLATE = r"{prompt_id}-(\d+)\.json"

# `--record-fixtures` 由 CLI 置位（`complete_json()` 签名固定，不加参数）。
RECORD_FIXTURES = False

# `.agent-task` 目录索引缓存：`(目录, prompt_id)` → (目录内的**文件清单**, payload_hash → bundle 路径)。
# 进程内共享，清单变化即失效（见 `_bundle_index()`；判据是文件清单而非目录 mtime —— mtime 粒度可能达
# 秒级，同一批内新写的 bundle 不会改变它，缓存就会返回缺新键的陈旧索引）。
_BUNDLE_INDEX_CACHE: dict[tuple[str, str], tuple[list[str], dict[str, Path]]] = {}

class SchemaError(ValueError):
    """LLM 响应不符合提示词自带的 JSON schema（文案只含路径与键名，不含响应内容）。"""


class AgentTasksPendingError(RuntimeError):
    """`agent` 后端缺回填结果：列出全部缺失文件，绝不伪造响应。"""

    def __init__(self, missing: list[Path]) -> None:
        self.missing = list(missing)
        listed = "、".join(_display_path(path) for path in self.missing)
        super().__init__(f"agent 后端缺少 {len(self.missing)} 个回填结果（不伪造、不回落模板）：{listed}")


# 可重试：传输 / HTTP / JSON 解析 / schema（`SchemaError` 是 `ValueError` 子类）/ 响应结构错位。
RETRYABLE_ERRORS = (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError)


# --------------------------------------------------------------------------------------
# JSON schema 校验（stdlib 子集实现：type/enum/const/required/properties/additionalProperties
# /items/prefixItems/minItems/maxItems/minLength）
# --------------------------------------------------------------------------------------

_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _matches_type(instance, type_name: str) -> bool:
    expected = _TYPE_CHECKS.get(type_name)
    if expected is None:
        raise SchemaError(f"schema 声明了不支持的 type: {type_name}")
    if isinstance(instance, bool) and type_name in {"integer", "number"}:
        return False
    return isinstance(instance, expected)


def validate_schema(instance, schema: dict, *, path: str = "$") -> None:
    """按提示词自带的 schema 校验响应；不合法即 `SchemaError`（消息不含响应值）。"""
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: schema 必须是 JSON 对象")
    expected_type = schema.get("type")
    if expected_type is not None:
        names = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_matches_type(instance, name) for name in names):
            raise SchemaError(f"{path}: 期望 {expected_type}，实际 {type(instance).__name__}")
    if "const" in schema and instance != schema["const"]:
        raise SchemaError(f"{path}: 取值必须等于 schema 常量")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaError(f"{path}: 取值不在 schema 枚举内")
    if isinstance(instance, str) and "minLength" in schema and len(instance) < schema["minLength"]:
        raise SchemaError(f"{path}: 长度 {len(instance)} 小于 minLength {schema['minLength']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise SchemaError(f"{path}: 元素数 {len(instance)} 小于 minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaError(f"{path}: 元素数 {len(instance)} 大于 maxItems {schema['maxItems']}")
        prefix_items = schema.get("prefixItems")
        for index, item in enumerate(instance):
            item_schema = None
            if isinstance(prefix_items, list) and index < len(prefix_items):
                item_schema = prefix_items[index]
            elif isinstance(schema.get("items"), dict):
                item_schema = schema["items"]
            if isinstance(item_schema, dict):
                validate_schema(item, item_schema, path=f"{path}[{index}]")
    if isinstance(instance, dict):
        for key in schema.get("required") or []:
            if key not in instance:
                raise SchemaError(f"{path}: 缺必填键 {key}")
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            extra = sorted(set(instance) - set(properties))
            if extra:
                raise SchemaError(f"{path}: 出现未声明键 {extra}")
        for key, value in instance.items():
            if key in properties:
                validate_schema(value, properties[key], path=f"{path}.{key}")


# --------------------------------------------------------------------------------------
# 提示词 / fixture / payload 哈希
# --------------------------------------------------------------------------------------

def prompt_path(prompt_id: str, prompt_version: str) -> Path:
    return PROMPTS_DIR / f"{prompt_id}.{prompt_version}.md"


def load_prompt(prompt_id: str, prompt_version: str) -> tuple[str, dict]:
    """→（发给模型的提示词全文，用于校验响应的 JSON schema）。schema 写在 ```json schema 块里。"""
    path = prompt_path(prompt_id, prompt_version)
    if not path.is_file():
        raise RuntimeError(f"提示词缺失: {path.name}")
    text = path.read_text(encoding="utf-8")
    match = SCHEMA_FENCE_RE.search(text)
    if match is None:
        raise RuntimeError(f"提示词缺少 ```json schema 块: {path.name}")
    try:
        schema = json.loads(match.group("schema"))
    except ValueError as exc:
        raise RuntimeError(f"提示词的 schema 不是合法 JSON: {path.name}") from exc
    return text, schema


def prompt_course_scope(prompt_id: str, prompt_version: str) -> list[str]:
    """模板 frontmatter 声明的课程作用域（`course_scope: ["15040"]`，plan § Data contracts 4 / F-401）。"""
    path = prompt_path(prompt_id, prompt_version)
    if not path.is_file():
        raise RuntimeError(f"提示词缺失: {path.name}")
    match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if match is None:
        raise RuntimeError(f"提示词缺少 frontmatter: {path.name}")
    field = COURSE_SCOPE_LINE_RE.search(match.group("body"))
    if field is None:
        raise RuntimeError(f"提示词 frontmatter 缺 course_scope: {path.name}")
    try:
        scope = json.loads(field.group("value"))
    except ValueError as exc:
        raise RuntimeError(f"提示词的 course_scope 不是合法 JSON 数组: {path.name}") from exc
    if not isinstance(scope, list) or not all(isinstance(item, str) and item for item in scope):
        raise RuntimeError(f"提示词的 course_scope 必须是非空字符串数组: {path.name}")
    return scope


def payload_hash(payload: dict) -> str:
    """payload 的稳定哈希（fixture 键；键序无关、非 ASCII 原样）。"""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()[:16]


def fixture_path(prompt_id: str, prompt_version: str) -> Path:
    return FIXTURES_DIR / f"{prompt_id}.{prompt_version}.json"


def _fixture_entry(prompt_id: str, prompt_version: str, payload: dict) -> dict:
    path = fixture_path(prompt_id, prompt_version)
    if not path.is_file():
        raise RuntimeError(f"missing fixture: {path.name}（{prompt_id}.{prompt_version} 无录制响应，不伪造、不回落模板）")
    document = json.loads(path.read_text(encoding="utf-8"))
    entry = (document.get("responses") or {}).get(payload_hash(payload))
    if not isinstance(entry, dict):
        raise RuntimeError(
            f"missing fixture: {path.name}#{payload_hash(payload)}（该 payload 无录制响应，不伪造、不回落模板）"
        )
    return entry


def record_fixture(prompt_id: str, prompt_version: str, payload: dict, response: dict, generator: dict) -> Path:
    """把「payload 稳定哈希 → 响应 + 来源元数据」写进录制文件（同键覆盖，键序固定 → 字节稳定）。"""
    path = fixture_path(prompt_id, prompt_version)
    document = {"prompt_id": prompt_id, "prompt_version": prompt_version, "responses": {}}
    if path.is_file():
        document = json.loads(path.read_text(encoding="utf-8"))
    responses = dict(document.get("responses") or {})
    responses[payload_hash(payload)] = {"generator": generator, "response": response}
    document["prompt_id"] = prompt_id
    document["prompt_version"] = prompt_version
    document["responses"] = {key: responses[key] for key in sorted(responses)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------
# `agent` 后端的任务包（运行态，不入 git）
# --------------------------------------------------------------------------------------

def agent_task_dir(course_code: str) -> Path:
    return COURSES_DIR / course_code / AGENT_TASK_DIRNAME


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _agent_result_path(bundle: Path) -> Path:
    return bundle.with_name(f"{bundle.stem}.result.json")


def _bundle_index(directory: Path, prompt_id: str) -> dict[str, Path]:
    """`payload_hash → bundle 路径` 索引（按文件清单记忆化，QC3-010 / W5）。

    逐 job 重建索引会把批次成本推成 O(n²)：`15040/.agent-task/` 实测 786–1196 个 bundle
    （平均 4543 B），读 + `json.loads` 每个约 33 µs，60 µs/文件 × 2 遍（`prepare_agent_tasks`
    + 每个 job 的 `_call_agent`）× n²/2 ≈ **86 秒**纯重复解析。

    失效判据 = **目录内的文件清单**（`glob` 结果，含名字）。不用目录 mtime：其粒度可能达秒级，
    同一批内新写的 bundle 不会改变它，缓存就会返回缺少新键的陈旧索引。清单枚举实测 7.5 ms/次，
    相对被省掉的逐文件解析（786 × 33 µs ≈ 26 ms）小一个量级，且语义精确 ——
    文件名变化 ⇔ 索引内容可能变化。
    """
    names = (
        sorted(
            path.name
            for path in directory.glob(f"{prompt_id}-*.json")
            if not path.name.endswith(".result.json")
            and re.fullmatch(BUNDLE_NAME_RE_TEMPLATE.format(prompt_id=re.escape(prompt_id)), path.name)
        )
        if directory.is_dir()
        else []
    )
    cache_key = (str(directory), prompt_id)
    cached = _BUNDLE_INDEX_CACHE.get(cache_key)
    if cached is not None and cached[0] == names:
        return cached[1]

    index: dict[str, Path] = {}
    for name in names:
        path = directory / name
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        key = existing.get("payload_hash")
        if isinstance(key, str) and key:
            index.setdefault(key, path)
    _BUNDLE_INDEX_CACHE[cache_key] = (names, index)
    return index


def _bundle_position(index: dict[str, Path], prompt_id: str) -> int:
    """索引里已有的最大编号（新 bundle 从它 +1 起编号）。"""
    highest = 0
    for path in index.values():
        match = re.fullmatch(BUNDLE_NAME_RE_TEMPLATE.format(prompt_id=re.escape(prompt_id)), path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def write_agent_bundle(
    prompt_id: str, prompt_version: str, payload: dict, *, index: dict[str, Path] | None = None
) -> Path:
    """写（或复用）该 payload 的任务包。同一 payload 复用既有编号，回填结果跨次运行仍然有效。

    `index` 由调用方传入时直接复用（`prepare_agent_tasks` 逐批构建一次，QC3-010 / W5）。
    """
    course_code = payload.get("course_code")
    if not isinstance(course_code, str) or not course_code:
        raise RuntimeError("agent 后端要求 payload 含 course_code（用于定位 .agent-task 目录）")
    directory = agent_task_dir(course_code)
    key = payload_hash(payload)
    index = _bundle_index(directory, prompt_id) if index is None else index
    existing_path = index.get(key)
    if existing_path is not None:
        return existing_path
    bundle = directory / f"{prompt_id}-{_bundle_position(index, prompt_id) + 1}.json"
    instructions, _schema = load_prompt(prompt_id, prompt_version)
    document = {
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "task_index": _bundle_position(index, prompt_id) + 1,
        "payload_hash": key,
        "expect_result": _agent_result_path(bundle).name,
        "instructions": instructions,
        "payload": payload,
    }
    directory.mkdir(parents=True, exist_ok=True)
    bundle.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 新 bundle 落盘 → 目录内文件清单变化，下次 `_bundle_index()` 自然重建；本批内把新键并入索引，
    # 使后续同 payload 的 job 复用同一编号（否则整批会各自重建、回到 O(n²)）。
    index[key] = bundle
    return bundle


def prepare_agent_tasks(course_code: str, jobs) -> list[Path]:
    """写全部任务包，返回仍缺回填的结果文件（供 CLI 一次性列出，不伪造）。

    目录索引**在整个批次内只构建一次**（QC3-010 / W5）：`indexes[prompt_id]` 构建后传给
    `write_agent_bundle()` 复用，逐 job 重建会把批次成本推成 O(n²)（见 `_bundle_index()`）。
    """
    directory = agent_task_dir(course_code)
    indexes: dict[str, dict[str, Path]] = {}
    missing: list[Path] = []
    for prompt_id, prompt_version, payload in jobs:
        if prompt_id not in indexes:
            indexes[prompt_id] = _bundle_index(directory, prompt_id)
        result = _agent_result_path(write_agent_bundle(prompt_id, prompt_version, payload, index=indexes[prompt_id]))
        if not result.is_file():
            missing.append(result)
    return missing


# --------------------------------------------------------------------------------------
# 三个后端 + 来源元数据
# --------------------------------------------------------------------------------------

def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}（只从环境变量读取，不写入仓库 / 日志 / 报错）")
    return value


def _model_id(backend: str) -> str:
    model = os.environ.get("ZIKAO_LLM_MODEL", "").strip()
    if model:
        return model
    if backend == "agent":
        return DEFAULT_AGENT_MODEL
    raise RuntimeError("缺少环境变量 ZIKAO_LLM_MODEL（只从环境变量读取，不写入仓库 / 日志 / 报错）")


def _live_generator(backend: str, model: str) -> dict:
    return {"backend": backend, "model": model, "generated_at": date.today().isoformat()}


def _recorded_generator(entry: dict, prompt_id: str, prompt_version: str, payload: dict) -> dict:
    generator = entry.get("generator")
    if not isinstance(generator, dict) or not all(
        generator.get(key) for key in ("backend", "model", "generated_at")
    ):
        raise RuntimeError(
            f"fixture 缺少 generator 元数据: {fixture_path(prompt_id, prompt_version).name}#{payload_hash(payload)}"
        )
    return {"backend": generator["backend"], "model": generator["model"], "generated_at": generator["generated_at"]}


def _parse_chat_response(raw: bytes) -> dict:
    envelope = json.loads(raw.decode("utf-8"))
    content = envelope["choices"][0]["message"]["content"]
    data = json.loads(content)
    if not isinstance(data, dict):
        raise SchemaError("响应不是 JSON 对象")
    return data


def _post_json(url: str, body: dict, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return response.read()


def _call_cli(prompt_id: str, prompt_version: str, payload: dict, schema: dict) -> tuple[dict, dict]:
    text, _schema = load_prompt(prompt_id, prompt_version)
    url = _required_env("ZIKAO_LLM_BASE_URL").rstrip("/") + "/chat/completions"
    api_key = _required_env("ZIKAO_LLM_API_KEY")
    model = _model_id("cli")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": text},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            data = _parse_chat_response(_post_json(url, body, headers))
            validate_schema(data, schema)
            return data, _live_generator("cli", model)
        except RETRYABLE_ERRORS as exc:
            last_error = exc
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(RETRY_BASE_SECONDS * (2**attempt))
    raise RuntimeError(
        f"{prompt_id}.{prompt_version}: cli 后端 {MAX_ATTEMPTS} 次尝试后失败（{type(last_error).__name__}），"
        "不放宽 schema、不填占位文本"
    )


def _call_agent(prompt_id: str, prompt_version: str, payload: dict, schema: dict) -> tuple[dict, dict]:
    result = _agent_result_path(write_agent_bundle(prompt_id, prompt_version, payload))
    if not result.is_file():
        raise AgentTasksPendingError([result])
    try:
        data = json.loads(result.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RuntimeError(f"agent 回填结果不是合法 JSON: {_display_path(result)}") from exc
    validate_schema(data, schema)
    return data, _live_generator("agent", _model_id("agent"))


def complete_json(prompt_id: str, prompt_version: str, payload: dict, *, backend: str = "cli") -> dict:
    """三个后端唯一入口：拿到响应后都经 `validate_schema()` 同一条路径校验。"""
    if backend not in BACKENDS:
        raise ValueError(f"未知后端: {backend!r}（可选 {'/'.join(BACKENDS)}）")
    _text, schema = load_prompt(prompt_id, prompt_version)
    if backend == "cli":
        response, generator = _call_cli(prompt_id, prompt_version, payload, schema)
    elif backend == "agent":
        response, generator = _call_agent(prompt_id, prompt_version, payload, schema)
    else:
        entry = _fixture_entry(prompt_id, prompt_version, payload)
        response = entry.get("response")
        if not isinstance(response, dict):
            raise RuntimeError(
                f"fixture 响应不是 JSON 对象: {fixture_path(prompt_id, prompt_version).name}#{payload_hash(payload)}"
            )
        generator = _recorded_generator(entry, prompt_id, prompt_version, payload)
    validate_schema(response, schema)
    if RECORD_FIXTURES and backend != "replay":
        record_fixture(prompt_id, prompt_version, payload, response, generator)
    return response


def generator_metadata(prompt_id: str, prompt_version: str, payload: dict, *, backend: str = "cli") -> dict:
    """该次调用的来源元数据（不发起模型调用）：`cli` / `agent` 取当天，`replay` 回放录制时的来源。"""
    if backend == "cli":
        return _live_generator("cli", _model_id("cli"))
    if backend == "agent":
        return _live_generator("agent", _model_id("agent"))
    if backend == "replay":
        return _recorded_generator(_fixture_entry(prompt_id, prompt_version, payload), prompt_id, prompt_version, payload)
    raise ValueError(f"未知后端: {backend!r}（可选 {'/'.join(BACKENDS)}）")
