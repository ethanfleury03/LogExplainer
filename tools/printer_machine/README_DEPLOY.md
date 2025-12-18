# Deploying to the printer machine (Python 2.7.5, stdlib-only)

This tool is **stdlib-only** and must run on the printer machine under **Python 2.7.5** with **no pip installs**.

## Safe deployment (read-only)

- Copy the repository directory (or at minimum the `src/` folder) onto the printer machine.
- Do **not** modify printer software or system packages.
- Run the tool with an explicit `PYTHONPATH` pointing to the copied `src/` directory.

## Example: copy to the machine

- Copy the whole folder (recommended for documentation + scripts):
  - `/path/to/LogExplainer/`
    - contains `src/log_explainer/...`

## Run commands (Python 2.7.5)

Verify Python version:

- `python -V`

Run help (src/ layout):

- `PYTHONPATH=/path/to/LogExplainer/src python -m log_explainer --help`

Run a sample invocation (still scaffolding; no logic yet):

- `PYTHONPATH=/path/to/LogExplainer/src python -m log_explainer --roots /opt/memjet/PDL/MJ6.5.0-2.el7 --log "example"`

## Important notes

- No internet, no pip, no third-party libraries.
- The tool is intended to be read-only; future implementations should avoid writing to printer paths.

## Portable ZIP app + hard write firewall (recommended)

This deployment mode allows you to place the tool anywhere (even `/`) while guaranteeing:

- **No writes anywhere** except the dedicated data directory (default: `/arrow-log-helper-data`)
- **Read-only scanning** of `/opt/memjet`
- **No symlink following** by default

### One-time setup (printer machine)

Create the writable data directory:

- `sudo mkdir -p /arrow-log-helper-data`

Make it writable for the technician user (pick ONE approach):

- **Simple (per prompt)**: `sudo chmod 777 /arrow-log-helper-data`
- **Safer**: `sudo chown <tech_user> /arrow-log-helper-data`

### Build the zip on a dev machine

From the repo root:

- `python tools/build/make_zip.py`

This produces:

- `ArrowLogHelper.zip`

### Copy + run on printer machine

Copy `ArrowLogHelper.zip` to the printer PC (can be anywhere, even `/`), then run:

- `python /ArrowLogHelper.zip`

Optional overrides:

- **Writable data dir override**: `ARROW_LOG_HELPER_DATA_DIR=/arrow-log-helper-data python /ArrowLogHelper.zip`
- **Scan roots override**: `ARROW_LOG_HELPER_ROOTS=/opt/memjet python /ArrowLogHelper.zip`

### Verify safety

In the GUI, confirm the banner shows:

- **Writable dir**: `/arrow-log-helper-data` (or your override)
- **Firewall**: `ON`
- **Scan roots**: `/opt/memjet` (or your override)

Optional filesystem check (should show no modified files under `/opt/memjet`):

- `date > /arrow-log-helper-data/marker.txt`
- Run one Analyze in the GUI
- `find /opt/memjet -type f -newer /arrow-log-helper-data/marker.txt | head`

(Expected: prints nothing.)


