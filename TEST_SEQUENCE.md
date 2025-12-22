# Error Debug Feature - Minimal Test Sequence

## Prerequisites

1. **Generate fixture index:**
   ```bash
   python tools/make_fixture_index.py
   # Creates: dev_storage/fixtures/index_fixture.json
   ```

2. **Start backend:**
   ```bash
   cd backend
   python main.py
   # Should see: "Database initialized" and "Uvicorn running on http://0.0.0.0:8000"
   ```

3. **Start frontend:**
   ```bash
   cd frontend/analyzer
   npm run dev
   # Should see: "Ready on http://localhost:3000"
   ```

4. **Set environment variables (frontend):**
   ```bash
   # In frontend/analyzer/.env.local
   NEXT_PUBLIC_DEV_AUTH_BYPASS=true
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

## Test Sequence

### 1. Upload Fixture Index → Search → View Details

**Steps:**
1. Navigate to `http://localhost:3000/tech/error-debug`
2. Click "Add Machine"
3. Fill in:
   - Display Name: `Test Printer`
   - Printer Model: `Test Model`
   - Printing Type: `Test Type`
4. Click "Create"
5. Click "Upload/Update Index" button for the new machine
6. Select `dev_storage/fixtures/index_fixture.json`
7. Wait for upload to complete
8. Click "Search" button
9. In search box, type: `connection failed`
10. Click "Search"
11. Verify results appear
12. Click on a result chunk
13. Verify details pane shows: Summary, Code, Metadata, Raw tabs

**Expected:**
- Machine created successfully
- Index uploads without errors
- Search returns results for "connection failed"
- Details pane shows chunk information

**Check backend logs for:**
```
Upload request: machine_id=..., user=..., role=TECHNICIAN
Upload: storage_mode=LOCAL, path=...
Upload SUCCESS: machine_id=..., version_id=..., chunks=5, errors=8
Search request: machine_id=..., query='connection failed'...
Search result: ... match_type=exact:1/partial:0, total_results=1, elapsed_ms=...
```

### 2. Upload Real Index → Search Exact Known Message

**Steps:**
1. If you have a real index from `tools/ingest.py`, upload it
2. Search for an exact error message you know exists in the index
3. Verify exact match returns results instantly

**Expected:**
- Exact match returns results immediately
- Backend log shows `match_type=exact:1`

### 3. Upload Second Version → Activate Old/New → Confirm Results Change

**Steps:**
1. Upload a second index version (can be same file or different)
2. Go to Versions page
3. Note which version is active
4. Activate the other version
5. Go back to Search page
6. Search for the same query
7. Verify results may differ (if versions differ)

**Expected:**
- Version activation works
- Cache is cleared (check logs for "Cache CLEARED")
- Search results reflect active version

**Check backend logs for:**
```
Activate request: machine_id=..., version_id=...
Cache CLEARED for machine_id=...: 1 entries removed
Activate SUCCESS: machine_id=..., version_id=...
```

### 4. Download Version → Open JSON

**Steps:**
1. Go to Versions page
2. Click "Download" button for any version
3. Verify file downloads as `index_Test_Printer_<version_id>.json`
4. Open downloaded file
5. Verify it's valid JSON with schema_version and created_at

**Expected:**
- File downloads with correct filename
- JSON is valid and contains expected fields

**Check backend logs for:**
```
Download request: machine_id=..., version_id=..., user=...
Download SUCCESS: machine_id=..., version_id=..., size=... bytes
```

### 5. Customer Role Returns 403 (Quick Check)

**Steps:**
1. In browser, navigate to: `http://localhost:3000/tech/error-debug?as=CUSTOMER`
2. Try to access the page
3. Should see "Access Denied" message

**Or test via curl:**
```bash
curl http://localhost:8000/api/error-debug/machines \
  -H "X-DEV-ROLE: CUSTOMER" \
  -H "X-DEV-USER: customer@example.com"
```

**Expected:**
- Returns 403 Forbidden
- Error message: "Access denied. Required role: ADMIN or TECHNICIAN, got: CUSTOMER"

**Check backend logs for:**
```
Access denied. Required role: ADMIN or TECHNICIAN, got: CUSTOMER
```

## Troubleshooting

### Issue: "Empty list / 401" in UI

**Check:**
1. Browser DevTools → Network tab → Check request headers
2. Should see `X-DEV-ROLE: TECHNICIAN` or `X-DEV-ROLE: ADMIN`
3. If missing, check `NEXT_PUBLIC_DEV_AUTH_BYPASS=true` in frontend env

**Backend log:**
```
Missing X-DEV-ROLE header. Required roles: ADMIN, TECHNICIAN
```

### Issue: Upload fails with validation error

**Check backend log:**
```
Upload request: machine_id=...
ERROR: Missing required field: schema_version
```

**Fix:** Ensure index JSON includes `schema_version` and `created_at` fields.

### Issue: Search returns no results

**Check backend log:**
```
Search result: ... match_type=exact:0/partial:0, total_results=0, elapsed_ms=...
```

**Possible causes:**
- No active index (check: "No active index uploaded" banner)
- Query doesn't match any error messages in index
- Cache issue (check for cache HIT/MISS logs)

### Issue: Cache shows stale results

**Check backend log for:**
```
Cache CLEARED for machine_id=...: X entries removed
```

**If missing:** Cache invalidation may not be working. Check that upload/activate/delete operations call `_clear_cache_for_machine()`.

### Issue: Windows path errors

**Check:**
- Backend logs show absolute paths (not relative)
- SQLite file path uses forward slashes in URI
- Local storage paths use `Path` objects (not string concatenation)

**Example log:**
```
Upload: storage_mode=LOCAL, path=C:\LogExplainer_clean\dev_storage\error_debug\...\...
```

## Success Criteria

All tests pass if:
- ✅ Fixture index uploads successfully
- ✅ Search returns results for known error messages
- ✅ Details pane shows chunk information
- ✅ Version activation works and clears cache
- ✅ Download works and returns valid JSON
- ✅ Customer role gets 403
- ✅ Backend logs show all key operations
- ✅ No Windows path issues

## Next Steps

After passing all tests:
1. Test with real printer-generated index
2. Test GCS storage (if configured)
3. Test with Postgres database (if configured)
4. Test email script functionality (if SMTP configured)

