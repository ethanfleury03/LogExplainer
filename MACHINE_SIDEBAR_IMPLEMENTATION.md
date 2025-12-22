# Machine Sidebar Implementation - Final Checklist

## ✅ Completed Items

### 1. Conditional Rendering (Error Debug Area Only)
- ✅ MachineSidebar only appears when `pathname.startsWith('/tech/error-debug')`
- ✅ Hidden on all other pages (Search, Library, Settings, etc.)
- ✅ Still requires TECHNICIAN/ADMIN role

### 2. Upload/Update Index Quick Action
- ✅ "Upload Index" button appears when a machine is selected
- ✅ Button shown below selected machine name
- ✅ Opens file picker directly (no modal needed)
- ✅ Uses same `uploadVersion` API client function
- ✅ Navigates to machine page after successful upload
- ✅ Shows "Uploading..." state during upload

### 3. Loading/Error States
- ✅ Skeleton loading state (3 animated placeholders) while fetching
- ✅ Clear error messages:
  - "Access denied. Check auth headers." for 401/403
  - "Backend unreachable. Check API URL." for network errors
  - Generic error message for other failures
- ✅ Retry button on error state
- ✅ Console logging for debugging (`MachineSidebar: Loaded X machines`)

### 4. Backend URL and Auth Headers
- ✅ Uses same `error-debug-client.ts` API client
- ✅ Same `API_BASE_URL` (defaults to `http://localhost:8000`)
- ✅ Same `getHeaders()` function that includes `X-DEV-ROLE` and `X-DEV-USER`
- ✅ Headers automatically included in all requests

### 5. Navigation Consistency
- ✅ Clicking "Error Debug" in app nav → `/tech/error-debug` (table page)
- ✅ Selecting machine in sidebar → `/tech/error-debug/[machineId]` (search page)
- ✅ URL is source of truth for selection (highlighting based on pathname)
- ✅ Machine list refreshes on pathname change

### 6. Additional Improvements
- ✅ Auto-refresh machine list when navigating between pages
- ✅ Better visual feedback for selected machine (highlight + upload button)
- ✅ Proper error handling in upload flow
- ✅ File input reset after upload

## Testing Checklist

### Basic Functionality
- [ ] Navigate to `/tech/error-debug` - sidebar should appear
- [ ] Navigate to `/` (Search) - sidebar should NOT appear
- [ ] Check browser DevTools → Network tab
  - [ ] Request to `/api/error-debug/machines` includes `X-DEV-ROLE: TECHNICIAN`
  - [ ] Response is 200 with machine list

### Machine Selection
- [ ] Click "Add Machine" → modal opens
- [ ] Create machine → list updates, navigates to machine page
- [ ] Click machine in list → navigates to `/tech/error-debug/[id]`
- [ ] Selected machine is highlighted

### Upload Flow
- [ ] Select a machine → "Upload Index" button appears
- [ ] Click "Upload Index" → file picker opens
- [ ] Select index.json → uploads successfully
- [ ] After upload → navigates to machine page
- [ ] Machine list refreshes

### Error States
- [ ] Stop backend → sidebar shows "Backend unreachable" error
- [ ] Click "Retry" → attempts to reload machines
- [ ] Test with CUSTOMER role → sidebar doesn't appear

## Debugging Tips

### If machines don't appear:

1. **Check Network Tab:**
   - Open DevTools → Network
   - Look for `GET /api/error-debug/machines`
   - Check request headers: Should include `X-DEV-ROLE: TECHNICIAN`
   - Check response: Should be 200 with JSON array

2. **Check Console:**
   - Look for `MachineSidebar: Loaded X machines` log
   - Check for any error messages

3. **Check Backend:**
   - Ensure backend is running on `http://localhost:8000`
   - Check backend logs for incoming requests
   - Verify database has machines

4. **Check Environment:**
   - `NEXT_PUBLIC_API_URL` should be set (or defaults to `http://localhost:8000`)
   - `NEXT_PUBLIC_DEV_AUTH_BYPASS` should be `true` (or `NODE_ENV !== 'production'`)

### Common Issues:

**Issue**: Sidebar shows "Backend unreachable"
- **Fix**: Check backend is running and `NEXT_PUBLIC_API_URL` is correct

**Issue**: Sidebar shows "Access denied"
- **Fix**: Check `X-DEV-ROLE` header is being sent (should be `TECHNICIAN` or `ADMIN`)

**Issue**: Machines exist in DB but sidebar is empty
- **Fix**: Check Network tab - likely auth header issue or wrong API URL

**Issue**: Upload button doesn't appear
- **Fix**: Ensure you're on `/tech/error-debug/[machineId]` page (not table page)

## File Structure

```
frontend/analyzer/
├── components/AppShell/
│   ├── MachineSidebar.tsx    ← New: Machine selector sidebar
│   ├── AppShell.tsx          ← Modified: Added MachineSidebar
│   └── Sidebar.tsx           ← Unchanged: App navigation
├── lib/api/
│   └── error-debug-client.ts ← Modified: Exported Machine interface
└── lib/auth.ts               ← Modified: Always return user in dev mode
```

## API Endpoints Used

- `GET /api/error-debug/machines` - List machines (with auth headers)
- `POST /api/error-debug/machines` - Create machine (with auth headers)
- `POST /api/error-debug/machines/{id}/versions` - Upload index (with auth headers)

All requests automatically include:
- `X-DEV-ROLE: TECHNICIAN` (or `ADMIN`)
- `X-DEV-USER: dev@example.com`

## Next Steps

1. Test the full flow: Add machine → Select → Upload index → Search
2. Verify upload works with fixture index from `tools/make_fixture_index.py`
3. Test error states (backend down, wrong auth, etc.)
4. Consider syncing top dropdown with sidebar selection (future enhancement)

