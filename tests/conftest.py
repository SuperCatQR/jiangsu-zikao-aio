"""pytest configuration: inject scripts with dash-names as importable modules."""
import sys
import importlib.util
from pathlib import Path

import pytest

# Add scripts directory to path
scripts_dir = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(scripts_dir))

# Create module aliases for dash-named scripts
_script_mappings = {
    "check_source_links": "check-source-links.py",
    "bootstrap_province": "bootstrap-province.py",
    "validate_publish_gate": "validate-publish-gate.py",
    "compute_page_maturity": "compute-page-maturity.py",
}

for module_name, file_name in _script_mappings.items():
    script_path = scripts_dir / file_name
    if script_path.exists():
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)


@pytest.fixture(autouse=True)
def restore_llm_roots():
    """每个用例后把 `llm_client` 的根恢复成默认（QC3-007 / C2-010 的测试隔离）。

    `build-course-content.py` 的 `_sync_roots()` 会把 fixture / 提示词 / `.agent-task` 三个根
    重定向到入口的 `ROOT`（副本仓装置需要它）。那三个根是模块级全局（`complete_json()` 没有 root
    参数，签名由 plan 锁死），因此必须显式恢复 —— 否则先跑的副本仓用例会污染后续用例。
    """
    from lib.course_pipeline import llm_client

    original = (llm_client.REPO_ROOT, llm_client.FIXTURES_DIR, llm_client.COURSES_DIR)
    yield
    llm_client.REPO_ROOT, llm_client.FIXTURES_DIR, llm_client.COURSES_DIR = original
