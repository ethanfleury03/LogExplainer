# Troubleshooting Backend Connection Issues

## Error: "Backend unreachable. Check API URL."

This error means the frontend cannot connect to the backend API.

## Quick Checks

### 1. Is the backend running?

Check if the backend is running on port 8000:

```bash
# Windows PowerShell
netstat -ano | findstr :8000

# Or try to access it directly
curl http://localhost:8000/health
```

**If not running, start it:**
```bash
cd backend
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Check API URL Configuration

The frontend uses `NEXT_PUBLIC_API_URL` environment variable or defaults to `http://localhost:8000`.

**Check your frontend environment:**
- Look for `.env.local` or `.env` file in `frontend/analyzer/`
- Should contain: `NEXT_PUBLIC_API_URL=http://localhost:8000`

**If missing, create it:**
```bash
# In frontend/analyzer/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEV_AUTH_BYPASS=true
```

**Restart the Next.js dev server after changing env vars:**
```bash
# Stop the server (Ctrl+C) and restart
cd frontend/analyzer
npm run dev
```

### 3. Check Browser Console

Open browser DevTools (F12) → Console tab and look for:
- `MachineSidebar: Fetching machines from http://localhost:8000/api/error-debug/machines`
- Any CORS errors
- Network errors

### 4. Check Network Tab

Open DevTools → Network tab:
1. Refresh the page
2. Look for request to `/api/error-debug/machines`
3. Check:
   - **Status**: Should be 200 (if backend is running)
   - **Request URL**: Should be `http://localhost:8000/api/error-debug/machines`
   - **Request Headers**: Should include `X-DEV-ROLE: TECHNICIAN`
   - **Response**: If 200, should show JSON array

### 5. Common Issues

#### Issue: Backend not running
**Symptom**: Network tab shows "Failed to fetch" or "ERR_CONNECTION_REFUSED"
**Fix**: Start the backend server

#### Issue: Wrong port
**Symptom**: Backend running on different port (e.g., 8001)
**Fix**: Update `NEXT_PUBLIC_API_URL` to match backend port

#### Issue: CORS error
**Symptom**: Console shows CORS policy error
**Fix**: Check backend CORS config allows `http://localhost:3000`

#### Issue: Backend crashed
**Symptom**: Backend was running but stopped
**Fix**: Check backend terminal for errors, restart backend

## Step-by-Step Debugging

1. **Start Backend:**
   ```bash
   cd backend
   python main.py
   ```
   Should see: "Uvicorn running on http://0.0.0.0:8000"

2. **Test Backend Directly:**
   ```bash
   curl http://localhost:8000/health
   ```
   Should return: `{"status": "healthy"}`

3. **Test API Endpoint:**
   ```bash
   curl http://localhost:8000/api/error-debug/machines -H "X-DEV-ROLE: TECHNICIAN" -H "X-DEV-USER: test@example.com"
   ```
   Should return: `[]` (empty array) or list of machines

4. **Check Frontend Env:**
   - Open `frontend/analyzer/.env.local`
   - Should have: `NEXT_PUBLIC_API_URL=http://localhost:8000`
   - Restart Next.js dev server

5. **Check Browser:**
   - Open DevTools → Console
   - Look for: `MachineSidebar: Fetching machines from...`
   - Check Network tab for the actual request

## Expected Console Output

When working correctly, you should see in browser console:
```
MachineSidebar: Fetching machines from http://localhost:8000/api/error-debug/machines
listMachines: Requesting http://localhost:8000/api/error-debug/machines with headers ...
listMachines: Success 0 machines
MachineSidebar: Loaded 0 machines
```

## If Still Not Working

1. **Check backend logs** for incoming requests
2. **Check browser Network tab** for the exact error
3. **Verify both servers are running:**
   - Backend: `http://localhost:8000`
   - Frontend: `http://localhost:3000`
4. **Try accessing backend directly in browser:**
   - `http://localhost:8000/health` should work
   - `http://localhost:8000/api/error-debug/machines` will need headers (use curl or Postman)

