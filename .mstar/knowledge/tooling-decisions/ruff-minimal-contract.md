---
module: python-quality-tooling
date: 2026-08-25
problem_type: tooling_decision
category: tooling-decisions
severity: medium
plan_id: audit-python-quality-contract
applies_when:
  - "Choosing lint rules for a docs/content repo with scripts/ + tests/"
  - "Declaring quality tools in requirements-dev.txt or CI"
tags:
  - ruff
  - lint
  - ci
  - requirements-dev
  - pyproject
---

# Minimal Ruff contract: E4/E7/E9 + F only

## Context

The repo declared `ruff`, `mypy`, `pytest-cov` in `requirements-dev.txt` and the README
mentioned quality tooling, but nothing enforced it: no config file, no CI step, no documented
command. Contributors installed tools and got no stable gate — the README claim was aspirational.

## Guidance

- **Pick a minimal bug-catching contract**: `[tool.ruff.lint] select = ["E4", "E7", "E9", "F"]`
  in `pyproject.toml`. E4/E7/E9 are pycodestyle **critical** classes (imports, statements,
  logic), F is pyflakes (unused imports/names). Style/format rules stay **off** — the goal is
  catching real bugs, not a style gate.
- **Per-file-ignores for repo conventions** (not blanket ignores):
  - `"tests/*" = ["E402"]` — tests import scripts via `sys.path.insert` before module imports.
  - `"scripts/migrate_*.py" = ["E701", "E702"]` — one-shot migration scripts keep compressed style.
- **Wire one CI step**: `ruff check scripts tests` in the build job after pytest.
- **Truthful declarations**: requirements-dev comments state what CI enforces
  (`ruff` enforced; `mypy` declared-not-enforced unless a config + step are added).
- Auto-fix mechanical findings (`ruff check --fix`) before baselining the rest; do not
  silence findings that indicate real bugs.

## Why This Matters

A minimal enforced contract beats a broad aspirational one: it keeps CI green from day one,
catches real defects, and makes `requirements-dev.txt` truthful. Scope creep (full `E`/`W`
style, `isort`, `mypy` strict) is deliberately deferred to avoid a large lint-refactor on a
docs/content repo.

## When to Apply

- Any Python repo with `scripts/` + `tests/` where quality tools are declared but not enforced.
- When a repo has no existing lint config and a low tolerance for lint noise.

## Examples

- `pyproject.toml` `[tool.ruff.lint]` with `select` + `per-file-ignores` (see repo root).
- `.github/workflows/deploy-pages.yml` `Run Ruff lint` step.
