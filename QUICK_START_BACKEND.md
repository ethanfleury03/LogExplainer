# Quick Start - Backend Connection

## The Error You're Seeing

"Backend unreachable. Check API URL." means the frontend can't connect to the backend.

## Quick Fix (2 steps)

### Step 1: Start the Backend

Open a terminal and run:

```bash
cd backend
python main.py
```

You should see:
```
INFO:     Database initialized
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Keep this terminal open** - the backend must stay running.

### Step 2: Verify Frontend Environment

Check if `frontend/analyzer/.env.local` exists and contains:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEV_AUTH_BYPASS=true
```

If the file doesn't exist, create it:

```bash
# In frontend/analyzer directory
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
echo NEXT_PUBLIC_DEV_AUTH_BYPASS=true >> .env.local
```

**Then restart your Next.js dev server** (stop with Ctrl+C and run `npm run dev` again).

## Verify It's Working

1. **Backend is running**: Check terminal shows "Uvicorn running on http://0.0.0.0:8000"
2. **Test backend directly**: Open browser to `http://localhost:8000/health` - should show `{"status": "healthy"}`
3. **Check browser console**: Open DevTools (F12) → Console tab
   - Should see: `MachineSidebar: Fetching machines from http://localhost:8000/api/error-debug/machines`
   - Should see: `listMachines: Success 0 machines` (or number of machines)

## If Still Not Working

Check browser DevTools → Network tab:
- Look for request to `/api/error-debug/machines`
- Check the request URL (should be `http://localhost:8000/api/error-debug/machines`)
- Check response status (should be 200)

See `TROUBLESHOOTING_BACKEND_CONNECTION.md` for more detailed debugging.

