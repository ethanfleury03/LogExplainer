# Logging Audit Report

**Repo Path:** `C:\Users\ethan\ArrowSystems\backend`
**Scan Timestamp:** 2025-12-19 11:49:54

## Scan Coverage

| Metric | Count |
|--------|-------|
| Python files discovered | 95 |
| Python files successfully scanned | 95 |
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
| Total method calls | 330 |

### structlog

| Metric | Count |
|--------|-------|
| Imports | 1 |
| `get_logger()` calls | 1 |
| Total method calls | 1 |

### Generic Logger Calls

| Metric | Count |
|--------|-------|
| Total method calls | 699 |

*Note: Logger calls where the logger variable source could not be determined.*

### Non-Logging Output

| Type | Count |
|------|-------|
| `print()` calls | 549 |

### Framework String Mentions / Imports

| Framework | Count |
|-----------|-------|
*Note: String mentions or imports, not necessarily logger usage.*

| fastapi | 5 |
| gunicorn | 1 |
| uvicorn | 1 |

### Top 10 Files by Logging Calls

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
| INFO | 464 |
| WARNING | 293 |
| ERROR | 171 |
| CRITICAL | 1 |
| EXCEPTION | 18 |

## Logger Configuration Overview

### Configuration Locations

| File | Line | Type |
|------|------|------|
| `ingest.py` | 73 | basicConfig |
| `logging_config.py` | 29 | basicConfig (JSON) |
| `logging_config.py` | 63 | structlog.configure (JSON) |
| `query.py` | 19 | basicConfig |
| `scripts\migrate_local_pdfs_to_gcs.py` | 26 | basicConfig |

### Framework Config References

| Framework | File Mentions |
|-----------|---------------|
| fastapi | 5 |
| gunicorn | 1 |
| uvicorn | 1 |


## Actionable Findings

⚠️ **Multiple `basicConfig()` calls detected:** 4

Having multiple `basicConfig()` calls can cause configuration conflicts. Consider consolidating to a single configuration point.

- `ingest.py:73`
- `logging_config.py:29`
- `query.py:19`
- `scripts\migrate_local_pdfs_to_gcs.py:26`

⚠️ **High `print()` usage outside scripts/ directories:**

| File | Print Calls |
|------|-------------|
| `ingest.py` | 104 |
| `query.py` | 33 |
| `utils\reset_index.py` | 31 |
| `utils\migration_runner.py` | 17 |
| `api.py` | 16 |
| `preload_models.py` | 14 |

Consider replacing `print()` calls with proper logging in production code.

⚠️ **Files using both `print()` and logger calls:**

| File | Print Calls | Logger Calls |
|------|-------------|-------------|
| `ingest.py` | 104 | 176 |
| `orchestrator.py` | 3 | 238 |
| `api.py` | 16 | 223 |
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
