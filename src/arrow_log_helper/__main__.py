from __future__ import absolute_import, print_function

import os
import sys


def _abs_real(path):
    try:
        p = os.path.abspath(path)
    except Exception:
        p = path
    try:
        p = os.path.realpath(p)
    except Exception:
        pass
    return p


def _mkdir_p(path):
    if not path:
        return
    if os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except Exception:
        # Race or permissions
        if not os.path.isdir(path):
            raise


def _setup_data_dir(data_dir):
    data_dir = _abs_real(data_dir)
    _mkdir_p(data_dir)

    subdirs = {
        "cache": os.path.join(data_dir, "cache"),
        "config": os.path.join(data_dir, "config"),
        "state": os.path.join(data_dir, "state"),
        "tmp": os.path.join(data_dir, "tmp"),
        "home": os.path.join(data_dir, "home"),
        "logs": os.path.join(data_dir, "logs"),
    }
    for _, p in sorted(subdirs.items()):
        _mkdir_p(p)
    return data_dir, subdirs


def _set_env_for_portable_writes(data_dir, subdirs):
    # Force all common writable targets inside DATA_DIR.
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["HOME"] = subdirs["home"]
    os.environ["XDG_CACHE_HOME"] = subdirs["cache"]
    os.environ["XDG_CONFIG_HOME"] = subdirs["config"]
    os.environ["XDG_STATE_HOME"] = subdirs["state"]
    os.environ["TMPDIR"] = subdirs["tmp"]
    os.environ["TEMP"] = subdirs["tmp"]
    os.environ["TMP"] = subdirs["tmp"]

    # Expose for UI banner/debug.
    os.environ["ARROW_LOG_HELPER_DATA_DIR"] = data_dir

    try:
        sys.dont_write_bytecode = True
    except Exception:
        pass


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Dev/CI escape hatch (keeps tests from needing a GUI or /arrow-log-helper-data).
    if os.environ.get("ARROW_LOG_HELPER_NO_GUI") == "1":
        try:
            sys.stdout.write("NO_GUI mode\n")
        except Exception:
            pass
        return 0

    data_dir = os.environ.get("ARROW_LOG_HELPER_DATA_DIR") or "/arrow-log-helper-data"
    # Remember where the process was launched from (useful for discovery when we chdir into DATA_DIR).
    try:
        os.environ["ARROW_LOG_HELPER_LAUNCH_CWD"] = os.getcwd()
    except Exception:
        pass
    data_dir, subdirs = _setup_data_dir(data_dir)
    _set_env_for_portable_writes(data_dir, subdirs)

    # Must refuse to run if DATA_DIR is not writable.
    from arrow_log_helper import write_firewall

    write_firewall.assert_writable_dir(data_dir)

    # Install write firewall BEFORE importing GUI/analyzer.
    write_firewall.install_write_firewall(data_dir, verbose=False)
    os.environ["ARROW_LOG_HELPER_FIREWALL"] = "1"

    # Run everything from inside DATA_DIR.
    try:
        os.chdir(data_dir)
    except Exception:
        # If we can't chdir, treat it as a safety failure.
        raise SystemExit("Failed to chdir to DATA_DIR: %s" % (data_dir,))

    from arrow_log_helper import gui

    return int(gui.main(argv) or 0)


if __name__ == "__main__":
    sys.exit(main())


