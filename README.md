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

## Repo name vs Python package name (expected)

- Repo folder: `LogExplainer/`
- Python import/package: `log_explainer` (underscores are required for Python imports)
- With the `src/` layout, the package lives at: `LogExplainer/src/log_explainer/`


