from __future__ import absolute_import, print_function

import json
import os


def _config_path(data_dir):
    return os.path.join(data_dir, "config", "selected_roots.json")


def load_selected_roots(data_dir):
    """
    Read JSON list from DATA_DIR/config/selected_roots.json if present, else None.
    """
    if not data_dir:
        return None
    path = _config_path(data_dir)
    if not os.path.isfile(path):
        return None
    try:
        f = open(path, "rb")
    except Exception:
        return None
    try:
        raw = f.read()
    finally:
        try:
            f.close()
        except Exception:
            pass
    try:
        obj = json.loads(raw.decode("utf-8", "replace") if hasattr(raw, "decode") else raw)
    except Exception:
        try:
            obj = json.loads(raw)
        except Exception:
            return None
    if isinstance(obj, list):
        # Normalize to list of strings.
        out = []
        for x in obj:
            try:
                out.append(str(x))
            except Exception:
                out.append(repr(x))
        return out
    return None


def save_selected_roots(data_dir, roots):
    """
    Write JSON list ONLY under DATA_DIR/config/.
    """
    if not data_dir:
        raise IOError("data_dir is required")
    cfg_dir = os.path.join(data_dir, "config")
    if not os.path.isdir(cfg_dir):
        try:
            os.makedirs(cfg_dir)
        except Exception:
            pass
    path = _config_path(data_dir)
    roots = roots or []
    data = []
    for r in roots:
        try:
            data.append(str(r))
        except Exception:
            data.append(repr(r))

    tmp_path = path + ".tmp"
    f = open(tmp_path, "wb")
    try:
        txt = json.dumps(data, indent=2, sort_keys=True)
        if not txt.endswith("\n"):
            txt += "\n"
        try:
            f.write(txt.encode("utf-8"))
        except Exception:
            f.write(txt)
    finally:
        try:
            f.close()
        except Exception:
            pass
    # Atomic-ish replace within DATA_DIR.
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    os.rename(tmp_path, path)
    return path


