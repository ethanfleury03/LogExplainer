# Logging Audit Report

**Repo Path:** `C:\LogExplainer_clean`
**Scan Timestamp:** 2025-12-19 14:03:02

**Total Lines (Physical):** 8306
**Non-Empty Lines:** 6942

## Scan Coverage

| Metric | Count |
|--------|-------|
| Python files discovered | 42 |
| Python files successfully scanned | 42 |
| Python files skipped (ignored path) | 0 |
| Python files skipped (decode error) | 0 |
| Python files skipped (read error) | 0 |
| Python files skipped (parse error) | 0 |

**Ignored directories:** .cache, .env, .git, .hg, .idea, .mypy_cache, .next, .pytest_cache, .ruff_cache, .svn, .venv, .vscode, build, dist, env, latest_model, logs, models, node_modules, out...

## Logging Usage Summary

### Standard Library Logging (`logging` module)

| Metric | Count |
|--------|-------|
| Imports | 0 |
| `getLogger()` calls | 0 |
| Total method calls | 0 |

### Generic/Unknown Logger Calls

| Metric | Count |
|--------|-------|
| Total method calls | 14 |

*Note: Logger calls where the logger variable source could not be determined.*

### Print Calls

| Location | Count |
|----------|-------|
| In `scripts/` directories | 0 |
| Outside `scripts/` | 35 |
| **Total** | 35 |

## Top Offenders

### Top 10 Files by Total Logger Calls

| File | Calls |
|------|-------|
| `tests\fixtures\sample_repo\module_a.py` | 5 |
| `tests\fixtures\rag_api_snippet.py` | 3 |
| `tests\fixtures\sample_repo\docstring_cases.py` | 3 |
| `tests\fixtures\async_decorator_test.py` | 2 |
| `tests\fixtures\sample_repo\top_level_only.py` | 1 |

### Top 10 Files by Print Calls

| File | Calls |
|------|-------|
| `tools\dev\run_search_demo.py` | 16 |
| `tools\dev\repo_scan.py` | 7 |
| `tools\dev\run_parse_demo.py` | 7 |
| `src\log_explainer\cli.py` | 2 |
| `src\arrow_log_helper\cli.py` | 1 |
| `src\arrow_log_helper\write_firewall.py` | 1 |
| `tools\dev\logInv.py` | 1 |

## Log Level Distribution

| Level | Count |
|-------|-------|
| INFO | 3 |
| ERROR | 11 |
| **Total** | **14** |

*Note: Total logger calls = 14. Level distribution sums must match this total.*

## Logger Configuration Overview

No explicit logging configuration found.

## Exceptions & Stack Traces

| Method | Count |
|--------|-------|
| `logger.exception()` | 0 |
| `logger.error(..., exc_info=True)` | 0 |
| `traceback.print_exc()` / `traceback.format_exc()` | 0 |

## Actionable Findings

⚠️ **High `print()` usage outside scripts/ directories:**

| File | Print Calls |
|------|-------------|
| `tools\dev\run_search_demo.py` | 16 |

Consider replacing `print()` calls with proper logging in production code.

ℹ️ **JSON logging not detected**

Consider enabling JSON formatting for structured logging, especially in production environments.

### Unknown Logger Variable Diagnostics

Top unknown logger variable names by call count:

| Variable Name | Call Count | Example Files |
|---------------|------------|---------------|
| `logger` | 14 | `tests\fixtures\sample_repo\module_a.py`, `tests\fixtures\rag_api_snippet.py`, `tests\fixtures\sample_repo\top_level_only.py` (+2 more) |
