# Error Debug Feature - Startup Verification Checklist

## 1. Backend Startup Entrypoint + Routing Registration ✅

**File**: `backend/main.py`

- ✅ Router included: `app.include_router(error_debug_routes.router)`
- ✅ Prefix: `/api/error-debug` (defined in `error_debug_routes.py`)
- ✅ CORS configured for `http://localhost:3000` and `http://127.0.0.1:3000`
- ✅ Database initialized: `init_db()` called on startup

**To verify:**
```bash
cd backend
python main.py
# Should see: "Uvicorn running on http://0.0.0.0:8000"
# Test: curl http://localhost:8000/health
```

## 2. DB Migrations / Table Creation ✅

**File**: `backend/utils/db.py`

- ✅ Auto-creation: `Base.metadata.create_all(bind=engine)` in `init_db()`
- ✅ Postgres: Uses `DATABASE_URL` env var if set
- ✅ SQLite fallback: Auto-creates `dev_storage/error_debug.db` if `DATABASE_URL` not set
- ✅ Absolute paths: Uses `Path(__file__).parent.parent.parent.resolve()` for stability

**To verify:**
```bash
# SQLite (no DATABASE_URL)
cd backend
python -c "from utils.db import init_db; init_db()"
# Check: ls -la ../dev_storage/error_debug.db

# Postgres (with DATABASE_URL)
export DATABASE_URL="postgresql://user:pass@localhost/dbname"
python -c "from utils.db import init_db; init_db()"
# Check: psql -c "\d error_debug_machines"
```

## 3. Auth Headers Actually Sent by Frontend ✅

**File**: `frontend/analyzer/lib/api/error-debug-client.ts`

- ✅ `getHeaders()` function includes `X-DEV-ROLE` and `X-DEV-USER` headers
- ✅ Dev mode: Always includes headers if `NEXT_PUBLIC_DEV_AUTH_BYPASS=true` or `NODE_ENV !== 'production'`
- ✅ Default role: `TECHNICIAN` if user not found
- ✅ All API calls use `getHeaders()` to include auth headers

**To verify:**
1. Open browser DevTools → Network tab
2. Navigate to `/tech/error-debug`
3. Check request headers for `X-DEV-ROLE: TECHNICIAN` or `X-DEV-ROLE: ADMIN`
4. If missing, check `NEXT_PUBLIC_DEV_AUTH_BYPASS` env var

**Fix if missing:**
```bash
# In frontend/analyzer/.env.local
NEXT_PUBLIC_DEV_AUTH_BYPASS=true
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 4. Storage Configuration Sanity ✅

### Local Fallback

**File**: `backend/utils/index_storage.py`

- ✅ Absolute paths: Uses `Path(__file__).parent.parent.parent.resolve()` for repo root
- ✅ Storage path: `{repo_root}/dev_storage/error_debug/{machine_id}/{version_id}.json`
- ✅ Auto-creates directories: `base_dir.mkdir(parents=True, exist_ok=True)`

**To verify:**
```bash
cd backend
python -c "from utils.index_storage import _get_local_storage_path; print(_get_local_storage_path('test-id', 'test-version'))"
# Should show absolute path ending in dev_storage/error_debug/test-id/test-version.json

# Test write
python -c "from utils.index_storage import save_index_file; save_index_file('test-id', 'test-version', b'{}'); print('OK')"
# Check: ls -la ../dev_storage/error_debug/test-id/
```

### GCS Mode

**File**: `backend/utils/index_storage.py`

- ✅ Checks `GCS_BUCKET` env var
- ✅ Optional `GCS_CREDENTIALS` for service account JSON
- ✅ Object path: `error_debug/{machine_id}/{version_id}.json`
- ✅ Content-type: `application/json`

**To verify:**
```bash
export GCS_BUCKET="your-bucket-name"
export GCS_CREDENTIALS="/path/to/credentials.json"  # Optional
cd backend
python -c "from utils.index_storage import save_index_file; save_index_file('test-id', 'test-version', b'{}'); print('OK')"
# Check GCS bucket: gsutil ls gs://your-bucket-name/error_debug/test-id/
```

## 5. Upload Limits (Local + Future) ✅

**File**: `backend/main.py`

- ✅ Uvicorn configured with reasonable limits
- ✅ Note: For Cloud Run, configure `max_request_size` in deployment settings
- ✅ Streaming read: Upload endpoint reads in 1MB chunks (not loading full file)

**To verify:**
```bash
# Test with large file (create test index > 10MB)
cd backend
python main.py
# In another terminal:
curl -X POST http://localhost:8000/api/error-debug/machines/{id}/versions \
  -H "X-DEV-ROLE: TECHNICIAN" \
  -F "file=@large_index.json"
# Should handle without memory issues
```

**For Cloud Run:**
```yaml
# cloud-run-config.yaml
apiVersion: serving.knative.dev/v1
kind: Service
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/execution-environment: gen2
    spec:
      containerConcurrency: 80
      timeoutSeconds: 300
      # Note: max_request_size is configured at Cloud Run service level
```

## 6. Index JSON Defaults Match Email Instructions ✅

**File**: `tools/ingest.py`

- ✅ Default `--root`: `/opt/memjet`
- ✅ Default `--out`: `/root/index.json`
- ✅ Default `--progress`: enabled
- ✅ Includes `schema_version: "1.0"`
- ✅ Includes `created_at` (ISO format)

**To verify:**
```bash
# Test with no arguments (should use defaults)
python tools/ingest.py
# Should output: "Indexing codebase: /opt/memjet"
# Should create: /root/index.json
# Should include: schema_version and created_at fields

# Check output
python -c "import json; idx=json.load(open('/root/index.json')); print('schema_version:', idx.get('schema_version')); print('created_at:', idx.get('created_at'))"
```

## 7. Search Correctness Tests ✅

**File**: `backend/utils/index_search.py`

- ✅ Exact match: Direct lookup in `error_index[normalized_message]`
- ✅ Partial match: Fallback to contains-based search (top 25)
- ✅ Normalization: lowercase, strip, collapse whitespace

**To test:**
1. Upload an index with known error message (e.g., "connection failed")
2. Search for exact message: "connection failed" → should return instantly
3. Search for substring: "connection" → should return fallback matches
4. Search for partial: "failed" → should return matches

**Test script:**
```python
# test_search.py
from backend.utils.index_search import search_chunk_index
import json

# Load test index
with open('test_index.json') as f:
    index = json.load(f)

# Test exact match
results = search_chunk_index("connection failed", index)
print(f"Exact match: {len(results)} results")

# Test partial match
results = search_chunk_index("connection", index)
print(f"Partial match: {len(results)} results")
```

## 8. Binary/Content Safety (Viewing Code) ✅

**File**: `backend/routes/error_debug_routes.py`

All endpoints require `require_role` dependency:
- ✅ `GET /api/error-debug/machines` - requires TECHNICIAN/ADMIN
- ✅ `POST /api/error-debug/machines` - requires TECHNICIAN/ADMIN
- ✅ `PUT /api/error-debug/machines/{id}` - requires TECHNICIAN/ADMIN
- ✅ `DELETE /api/error-debug/machines/{id}` - requires TECHNICIAN/ADMIN
- ✅ `GET /api/error-debug/machines/{id}/versions` - requires TECHNICIAN/ADMIN
- ✅ `POST /api/error-debug/machines/{id}/versions` - requires TECHNICIAN/ADMIN
- ✅ `GET /api/error-debug/machines/{id}/versions/{id}/download` - requires TECHNICIAN/ADMIN
- ✅ `POST /api/error-debug/search` - requires TECHNICIAN/ADMIN
- ✅ `POST /api/error-debug/email-ingest` - requires TECHNICIAN/ADMIN

**To verify:**
```bash
# Test without auth header (should get 403)
curl http://localhost:8000/api/error-debug/machines
# Expected: {"detail": "Missing X-DEV-ROLE header..."}

# Test with CUSTOMER role (should get 403)
curl http://localhost:8000/api/error-debug/machines \
  -H "X-DEV-ROLE: CUSTOMER"
# Expected: {"detail": "Access denied. Required role: ADMIN or TECHNICIAN, got: CUSTOMER"}

# Test with TECHNICIAN role (should succeed)
curl http://localhost:8000/api/error-debug/machines \
  -H "X-DEV-ROLE: TECHNICIAN" \
  -H "X-DEV-USER: tech@example.com"
# Expected: [] (empty list or machine data)
```

## Quick Start Verification

Run these commands to verify everything works:

```bash
# 1. Start backend
cd backend
python main.py
# Should see: "Uvicorn running on http://0.0.0.0:8000"

# 2. In another terminal, test health
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# 3. Test auth (should fail without header)
curl http://localhost:8000/api/error-debug/machines
# Expected: 403 error

# 4. Test auth (should succeed with header)
curl http://localhost:8000/api/error-debug/machines \
  -H "X-DEV-ROLE: TECHNICIAN" \
  -H "X-DEV-USER: tech@example.com"
# Expected: [] (empty list)

# 5. Start frontend
cd frontend/analyzer
npm run dev
# Should see: "Ready on http://localhost:3000"

# 6. Navigate to http://localhost:3000/tech/error-debug
# Should see machine table (empty initially)
# Check browser DevTools → Network tab for X-DEV-ROLE header
```

## Common Issues & Fixes

### Issue: "Empty list / 401" in UI
**Fix**: Check that `NEXT_PUBLIC_DEV_AUTH_BYPASS=true` is set in frontend env

### Issue: "Permission denied" writing to dev_storage
**Fix**: Check that `dev_storage/` directory is writable:
```bash
chmod -R 755 dev_storage/
```

### Issue: Database tables not created
**Fix**: Ensure `init_db()` is called on startup (it is in `main.py`)

### Issue: CORS errors in browser
**Fix**: Check that backend CORS allows `http://localhost:3000` (it does)

### Issue: Upload fails with large files
**Fix**: Check uvicorn limits and ensure streaming read is used (it is)

