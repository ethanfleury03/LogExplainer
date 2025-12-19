# Logging Audit Report

**Repo Path:** `C:\Users\ethan\ArrowSystems\backend`
**Scan Timestamp:** 2025-12-19 12:02:16

## Scan Coverage

| Metric | Count |
|--------|-------|
| Python files discovered | 97 |
| Python files successfully scanned | 97 |
| Python files skipped (ignored path) | 0 |
| Python files skipped (decode error) | 0 |
| Python files skipped (read error) | 0 |

**Ignored directories:** .cache, .env, .git, .hg, .idea, .mypy_cache, .next, .pytest_cache, .ruff_cache, .svn, .venv, .vscode, build, dist, env, latest_model, logs, models, node_modules, out...

## Logging Usage Summary

### Standard Library Logging (`logging` module)

| Metric | Count |
|--------|-------|
| Imports | 20 |
| `getLogger()` calls | 14 |
| Total method calls | 1038 |

### structlog

| Metric | Count |
|--------|-------|
| Imports | 1 |
| `get_logger()` calls | 1 |
| Total method calls | 1 |

### Non-Logging Output

| Type | Count |
|------|-------|
| `print()` calls | 551 |

## Top Offenders

### Top 10 Files by Total Logger Calls

| File | Calls |
|------|-------|
| `orchestrator.py` | 238 |
| `api.py` | 223 |
| `ingest.py` | 176 |
| `utils\simple_delete.py` | 51 |
| `routes\admin_routes.py` | 37 |
| `utils\delete_runner.py` | 37 |
| `scripts\migrate_local_pdfs_to_gcs.py` | 35 |
| `utils\gcs_client.py` | 34 |
| `utils\single_file_ingestion.py` | 25 |
| `rag\startup_downloader.py` | 19 |

### Top 10 Files by Print Calls

| File | Calls |
|------|-------|
| `ingest.py` | 104 |
| `scripts\verify_document_counts.py` | 45 |
| `scripts\doc_diagnose.py` | 41 |
| `scripts\cleanup_orphaned_documents.py` | 39 |
| `query.py` | 33 |
| `utils\reset_index.py` | 31 |
| `scripts\check_rag_offline.py` | 28 |
| `scripts\upload_index_to_gcs.py` | 28 |
| `scripts\find_orphaned_documents.py` | 27 |
| `scripts\reconcile_docs.py` | 27 |

## Log Level Distribution

| Level | Count |
|-------|-------|
| DEBUG | 83 |
| INFO | 471 |
| WARNING | 290 |
| ERROR | 176 |
| CRITICAL | 1 |
| EXCEPTION | 18 |

## Logger Configuration Overview

### Configuration Locations

| File | Line | Type | Entry Point | JSON |
|------|------|------|-------------|------|
| `ingest.py` | 73 | basicConfig | import-time | No |
| `logging_config.py` | 29 | basicConfig | guarded | Yes |
| `logging_config.py` | 63 | structlog.configure | guarded | Yes |
| `query.py` | 19 | basicConfig | import-time | No |
| `scripts\migrate_local_pdfs_to_gcs.py` | 26 | basicConfig | import-time | No |

*Entry Point: 'import-time' = executed at module import (high risk), 'guarded' = inside function or if __name__ == '__main__' (lower risk)*


## Exceptions & Stack Traces

| Method | Count |
|--------|-------|
| `logger.exception()` | 18 |
| `logger.error(..., exc_info=True)` | 114 |
| `traceback.print_exc()` / `traceback.format_exc()` | 6 |

### Bare `except:` Blocks

| File | Line |
|------|------|
| `api.py` | 3654 |
| `api.py` | 5317 |
| `api.py` | 6629 |
| `api.py` | 6636 |
| `ingest.py` | 2451 |
| `orchestrator.py` | 770 |
| `orchestrator.py` | 787 |
| `query.py` | 163 |
| `query.py` | 177 |

*Note: Bare except blocks may hide exceptions. Consider using `except Exception:` or specific exception types.*

## Actionable Findings

⚠️ **Multiple `basicConfig()` calls detected:** 4

Having multiple `basicConfig()` calls can cause configuration conflicts. Consider consolidating to a single configuration point.

| File | Line | Entry Point Likelihood |
|------|------|------------------------|
| `ingest.py` | 73 | import-time (⚠️ High risk) |
| `logging_config.py` | 29 | guarded (✓ Lower risk) |
| `query.py` | 19 | import-time (⚠️ High risk) |
| `scripts\migrate_local_pdfs_to_gcs.py` | 26 | import-time (⚠️ High risk) |

⚠️ **High `print()` usage outside scripts/ directories:**

| File | Print Calls |
|------|-------------|
| `ingest.py` | 104 |
| `query.py` | 33 |
| `utils\reset_index.py` | 31 |
| `api.py` | 18 |
| `utils\migration_runner.py` | 17 |
| `preload_models.py` | 14 |

Consider replacing `print()` calls with proper logging in production code.

⚠️ **Files using both `print()` and logger calls:**

| File | Print Calls | Logger Calls |
|------|-------------|-------------|
| `ingest.py` | 104 | 176 |
| `api.py` | 18 | 223 |
| `orchestrator.py` | 3 | 238 |
| `query.py` | 33 | 2 |
| `utils\migration_runner.py` | 17 | 16 |
| `scripts\find_orphaned_documents.py` | 27 | 2 |
| `rag\startup_downloader.py` | 7 | 19 |
| `rag_pipeline.py` | 6 | 15 |
| `config\env.py` | 2 | 10 |
| `utils\audit_log.py` | 2 | 3 |

Consider standardizing on logging for consistent output handling.

✅ **JSON logging is enabled:**

- `logging_config.py:29` (basicConfig)
- `logging_config.py:63` (structlog.configure)
