# LogExplainer

Tool concept (future): take a printer log snippet -> locate relevant code in a repo -> extract the function(s) involved -> generate a human-readable explanation/report.

**V0 scaffolding only, no logic yet.**

## Constraints (non-negotiable)

- **Target runtime**: Python 2.7.5 (CentOS/RHEL-era).
- **Stdlib only**: everything deployed to the printer machine must be pure Python 2.7 **standard library**.
- **No pip on target machine**: assume no internet and no dependency installs.
- **Read-only safety**: the tool must not modify printer software or repos; it should only read (and ideally run in read-only environments).

## Safety constraints

- Do not modify any files on the printer machine (no edits, no installs, no writes to protected paths).
- Any future scanning/searching must be read-only and should be conservative about performance.

## Planned next modules (not implemented yet)

This repo intentionally contains only scaffolding today. Intended future modules:

- **normalize**: normalize log lines, timestamps, error codes, and stack traces into a search-friendly form.
- **search**: search across configured roots for relevant files/symbols (read-only).
- **extract**: extract candidate functions/classes and surrounding context for explanation.
- **report**: generate a short explanation + evidence trail (files/lines) and export a report.

## How to run

From the repo root (development):

- `PYTHONPATH=src python -m log_explainer --help`

Or use the convenience script:

- `./run_py2.sh --help`

## Run GUI (Arrow Log Helper V1 UI, stubbed)

From the `LogExplainer/` directory:

- `PYTHONPATH=src python -m arrow_log_helper.gui`

Or via the optional CLI flag:

- `PYTHONPATH=src python -m arrow_log_helper.cli --gui`

## How to run (printer machine)

On the printer machine (or any locked-down host), the primary entrypoint is the single file `RUN_ME.py`.

- **Copy the repo folder** (this project is **stdlib-only**; no installs required)
- **Run**:
  - `python RUN_ME.py`

Safety notes:

- **Read-only**: current scaffold does not scan the filesystem or modify any external paths.
- **Stdlib-only**: no third-party dependencies.

Notes for maintainers:

- `run_py2.sh` is kept for developer convenience; **`RUN_ME.py` is the primary entrypoint** for technicians.

## Repo name vs Python package name (expected)

- Repo folder: `LogExplainer/`
- Python import/package: `log_explainer` (underscores are required for Python imports)
- With the `src/` layout, the package lives at: `LogExplainer/src/log_explainer/`

## Manual Testing Instructions

### Demo Mode

1. Set the demo root environment variable:
   ```bash
   export ARROW_LOG_HELPER_DEMO_ROOT=tests/fixtures/sample_repo
   ```

2. Run the GUI:
   ```bash
   python RUN_ME.py
   ```

3. Test the following features:
   - Verify the scan roots display shows the demo root
   - Paste a sample log line (e.g., from `tests/fixtures/sample_repo`):
     ```
     2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE
     ```
   - Click "Analyze" and verify:
     - Match list populates with confidence percentages and locations
     - Status updates during scanning
     - Selecting a match updates the right detail view
     - Summary section shows function/enclosure info
     - Metadata section shows key/value pairs
     - Code Block tab shows extracted code
     - Matched Line tab shows the exact matched line
     - Raw JSON tab shows the structured bundle
   - Click "Export JSON" and verify file is created in DATA_DIR
   - Click "Copy JSON" and verify JSON is copied to clipboard
   - Click "Help" to view safety guarantees

### Real Scan Mode

1. Set scan roots to a real codebase path:
   ```bash
   export ARROW_LOG_HELPER_ROOTS=/opt/memjet
   ```
   Or use the "Change..." button in the GUI to set roots interactively.

2. Run the GUI:
   ```bash
   python RUN_ME.py
   ```

3. Paste a real log line from the printer software

4. Click "Analyze" and verify:
   - All matches are listed with confidence percentages
   - Match details are correctly displayed
   - Export and Copy JSON work correctly

### Running Unit Tests

Run all unit tests including the new ui_bundle tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py"
```

## Error Debug (Local Dev)

The Error Debug feature allows technicians to manage printer machines, upload codebase indexes, and search for error messages.

### Quick Setup

Run the unified setup script to configure everything:

```powershell
.\setup.ps1
```

This script will:
- Check Python installation
- Create/activate virtual environment
- Install backend dependencies
- Initialize database
- Configure SMTP (optional)

### Running the Application

**Terminal 1 - Backend:**
```bash
# Run from repo root (recommended)
python -m uvicorn backend.main:app --reload --port 8000

# Or run from backend directory
cd backend
python -m uvicorn main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend/analyzer
npm install  # First time only
npm run dev
```

Then navigate to `http://localhost:3000/tech/error-debug`

### SMTP Configuration

**Easiest Option - Mailtrap (Recommended for Development):**
```powershell
.\scripts\setup-mailtrap-quick.ps1
```
- Free tier available
- No App Passwords needed
- No 2FA required
- Emails are captured (not actually sent) - perfect for testing
- View emails in web interface at https://mailtrap.io/inboxes

**Gmail Setup (For Production):**
```powershell
.\scripts\set-smtp-permanent.ps1 -Gmail
```
- Requires App Password (generate at https://myaccount.google.com/apppasswords)
- Requires 2FA enabled
- Actually sends emails

**Other SMTP Providers:**
```powershell
.\scripts\set-smtp-permanent.ps1
```

**Verify Configuration:**
```powershell
.\scripts\verify-smtp.ps1 -TestConnection
```

The configuration is saved to `.env` in the root directory and will persist across restarts.

### Usage

1. Navigate to `http://localhost:3000/tech/error-debug`
2. Add a machine (display name, printer model, printing type)
3. Upload an index JSON file (generated by `tools/ingest.py` on printer)
4. Search for error messages in the active index
5. Manage index versions (upload new, activate old, delete)

### Generating Index on Printer

1. Email script to technician: Use "Email Script" button in UI
2. On printer: Save `ingest.py` to `/root/ingest.py`
3. Run: `python /root/ingest.py` (defaults: `--root /opt/memjet --out /root/index.json`)
4. Upload `/root/index.json` to the portal

### Database

- **Postgres**: Set `DATABASE_URL` environment variable
- **SQLite**: Automatically used if `DATABASE_URL` not set (stored in `dev_storage/error_debug.db`)

Tables are auto-created on first run.


