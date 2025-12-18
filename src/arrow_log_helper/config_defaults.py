from __future__ import absolute_import

# Data-only defaults for Arrow Log Helper (no logic in this module).

DEFAULT_ROOTS = [
    "/opt/memjet/PDL/MJ6.5.0-2.el7",
    "/opt/memjet/dksg-pdl/MJ5.2.1-1.el7",
]

DEFAULT_INCLUDE_EXT = [".py"]

DEFAULT_EXCLUDE_DIRS = [
    # Common build / dependency / cache folders
    "node_modules",
    "dist",
    "build",
    "out",
    ".next",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
]

# Step 2 defaults (search limits)
DEFAULT_MAX_RESULTS = 10
DEFAULT_MAX_FILE_BYTES = 10485760  # 10 * 1024 * 1024


