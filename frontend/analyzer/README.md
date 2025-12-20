# Error Analyzer UI

Next.js dashboard for the Error Analyzer tool, deployed as a Cloud Run service and mounted under the portal domain at `/tools/analyzer`.

## Development

1. Install dependencies:
   ```bash
   npm install
   ```

2. Copy `.env.example` to `.env.local`:
   ```bash
   cp .env.example .env.local
   ```

3. For local development, edit `.env.local`:
   ```
   NEXT_PUBLIC_BASE_PATH=
   NEXT_PUBLIC_ANALYZER_API_URL=
   NEXT_PUBLIC_DEV_AUTH_BYPASS=true
   ```

4. Run the development server:
   ```bash
   npm run dev
   ```

5. Access at `http://localhost:3000`

## Testing Roles

When `NEXT_PUBLIC_DEV_AUTH_BYPASS=true`, you can override the role via query parameter:
- `http://localhost:3000?as=admin` - Admin role
- `http://localhost:3000?as=tech` - Tech role (default)
- `http://localhost:3000?as=customer` - Customer role

## Production

Set environment variables:
- `NEXT_PUBLIC_BASE_PATH=/tools/analyzer`
- `NEXT_PUBLIC_ANALYZER_API_URL=` (empty for relative paths)
- `NEXT_PUBLIC_DEV_AUTH_BYPASS=false` (or unset)

Build:
```bash
npm run build
npm start
```

## Architecture

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS + shadcn/ui components
- **State**: React hooks + TanStack Query (when needed)
- **Auth**: Dev bypass for local; portal integration for production (TODO)
- **Resizable Panes**: react-resizable-panels

## Features

- **Tri-pane Layout**: Resizable search results and details panes
- **Role-based Access**: Admin, Tech, Customer roles with gating
- **Error Key Grouping**: Results grouped by error key, collapsed by default
- **Search & Live Scan**: Library search and live scanning (stubbed)
- **Index Management**: Admin-only index management (stubbed)

