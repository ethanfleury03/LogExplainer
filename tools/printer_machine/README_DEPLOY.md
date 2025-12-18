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


