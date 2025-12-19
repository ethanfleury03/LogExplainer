# Repository Scan Report

**Repo Path:** `C:\Users\ethan\ArrowSystems\backend`
**Scan Timestamp:** 2025-12-19 10:52:45
**Total Files Scanned:** 94
**Python Files:** 94
**Exclusions:** .cache, .env, .git, .hg, .idea, .mypy_cache, .next, .pytest_cache, .ruff_cache, .svn...

## Logging Usage Summary

### Standard Library Logging (`logging` module)

| Metric | Count |
|--------|-------|
| Imports | 20 |
| `getLogger()` calls | 16 |
| Total method calls | 1029 |

### structlog

| Metric | Count |
|--------|-------|
| Imports | 1 |
| `get_logger()` calls | 2 |
| Total method calls | 17 |

### Non-Logging Output

| Type | Count |
|------|-------|
| `print()` calls | 549 |

### Framework Logger Usage

| Framework | Count |
|-----------|-------|
| gunicorn | 5 |
| uvicorn | 15 |

### Top 10 Files by Logging Calls

| File | Calls |
|------|-------|
| `orchestrator.py` | 238 |
| `api.py` | 222 |
| `ingest.py` | 176 |
| `utils\simple_delete.py` | 51 |
| `routes\admin_routes.py` | 37 |
| `utils\delete_runner.py` | 37 |
| `scripts\migrate_local_pdfs_to_gcs.py` | 35 |
| `utils\gcs_client.py` | 34 |
| `utils\single_file_ingestion.py` | 25 |
| `config\env.py` | 20 |

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
| DEBUG | 85 |
| INFO | 473 |
| WARNING | 297 |
| ERROR | 172 |
| CRITICAL | 1 |
| EXCEPTION | 18 |

## Logger Configuration Overview

### Configuration Locations

| File | Line | Type |
|------|------|------|
| `ingest.py` | 73 | basicConfig |
| `logging_config.py` | 29 | basicConfig |
| `logging_config.py` | 63 | structlog.configure |
| `query.py` | 19 | basicConfig |
| `scripts\migrate_local_pdfs_to_gcs.py` | 26 | basicConfig |

**JSON Formatting Detected:** No

## Repo Health Snapshot

### Bytecode Files (Read-Only Count)

| Type | Count |
|------|-------|
| `__pycache__/` directories | 0 |
| `*.pyc` files | 0 |

### TODO/FIXME Comments

**Total:** 2

| File | Count |
|------|-------|
| `api.py` | 2 |

### Test Files

**Total test files discovered:** 19

### Largest Python Files (by LOC)

| File | Lines of Code |
|------|---------------|
| `api.py` | 5633 |
| `orchestrator.py` | 3612 |
| `ingest.py` | 3390 |
| `routes\admin_routes.py` | 1795 |
| `utils\gcs_client.py` | 644 |
| `utils\database_manager.py` | 545 |
| `utils\document_metadata.py` | 538 |
| `utils\simple_delete.py` | 497 |
| `rag_pipeline.py` | 412 |
| `utils\db.py` | 369 |

**Total Python LOC:** 26580
