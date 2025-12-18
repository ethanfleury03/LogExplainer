from __future__ import absolute_import, print_function

import os

try:
    import shutil
except Exception:
    shutil = None


_FIREWALL_INSTALLED = False
_ORIGINALS = None


def _norm_abs_real(path):
    if path is None:
        return None
    try:
        p = os.path.abspath(path)
    except Exception:
        p = path
    try:
        p = os.path.realpath(p)
    except Exception:
        pass
    return p


def is_path_within(path, root):
    """
    Return True if `path` is within `root` (inclusive), using normalized absolute real paths.
    """
    p = _norm_abs_real(path)
    r = _norm_abs_real(root)
    if not p or not r:
        return False
    # Normalize case on Windows (best-effort).
    try:
        if os.name == "nt":
            p = p.lower()
            r = r.lower()
    except Exception:
        pass

    if p == r:
        return True

    # Ensure boundary on directory match.
    sep = os.sep
    if not r.endswith(sep):
        r = r + sep
    return p.startswith(r)


def assert_writable_dir(path):
    """
    Verify directory is writable by creating and deleting a small temp file inside it.
    Raises IOError on failure.
    """
    path = _norm_abs_real(path)
    if not path or not os.path.isdir(path):
        raise IOError("Not a directory: %r" % (path,))

    name = ".alh_write_test_%s" % (os.getpid(),)
    test_path = os.path.join(path, name)
    try:
        f = open(test_path, "wb")
        try:
            f.write(b"ok\n")
        finally:
            try:
                f.close()
            except Exception:
                pass
        try:
            os.remove(test_path)
        except Exception:
            try:
                os.unlink(test_path)
            except Exception:
                pass
    except Exception as e:
        raise IOError("DATA_DIR is not writable: %s (%r)" % (path, e))


def _raise_blocked(path):
    raise IOError("Write blocked by Arrow Log Helper firewall: %s" % (path,))


def _should_block_open(path, mode, allowed_root):
    # Only block on write/append/update modes.
    mode = mode or "r"
    m = mode.lower()
    writey = ("w" in m) or ("a" in m) or ("+" in m) or ("x" in m)
    if not writey:
        return False
    if is_path_within(path, allowed_root):
        return False
    return True


def _should_block_os_open(path, flags, allowed_root):
    # Best-effort detection of write intent.
    try:
        write_flags = 0
        for nm in ("O_WRONLY", "O_RDWR", "O_APPEND", "O_CREAT", "O_TRUNC"):
            if hasattr(os, nm):
                write_flags |= getattr(os, nm)
        if flags & write_flags:
            if not is_path_within(path, allowed_root):
                return True
    except Exception:
        pass
    return False


def is_installed():
    return bool(_FIREWALL_INSTALLED)


def uninstall_write_firewall():
    """
    Restore original functions if a firewall was installed.
    Intended for tests only.
    """
    global _FIREWALL_INSTALLED, _ORIGINALS
    if not _FIREWALL_INSTALLED or not _ORIGINALS:
        return

    orig = _ORIGINALS
    _ORIGINALS = None
    _FIREWALL_INSTALLED = False

    # Restore open
    if orig.get("builtin_open_mod") and orig.get("builtin_open_name"):
        try:
            setattr(orig["builtin_open_mod"], orig["builtin_open_name"], orig["builtin_open"])
        except Exception:
            pass

    # Restore os fns
    for name in ("remove", "unlink", "rename", "rmdir"):
        if name in orig:
            try:
                setattr(os, name, orig[name])
            except Exception:
                pass
    if "os_open" in orig and hasattr(os, "open"):
        try:
            os.open = orig["os_open"]
        except Exception:
            pass

    # Restore shutil fns
    if shutil is not None:
        for name in ("move", "rmtree"):
            if name in orig:
                try:
                    setattr(shutil, name, orig[name])
                except Exception:
                    pass


def install_write_firewall(allowed_write_root, verbose=False):
    """
    Install a hard write firewall. Blocks writes/deletes/moves outside allowed_write_root.
    """
    global _FIREWALL_INSTALLED, _ORIGINALS

    allowed_write_root = _norm_abs_real(allowed_write_root)
    if not allowed_write_root:
        raise IOError("allowed_write_root is required")
    if not os.path.isdir(allowed_write_root):
        raise IOError("allowed_write_root is not a directory: %r" % (allowed_write_root,))

    # Already installed? re-install is idempotent.
    if _FIREWALL_INSTALLED:
        return

    # Locate builtin open module for py2/py3.
    try:
        import __builtin__ as builtins_mod  # py2
        builtin_open_name = "open"
    except Exception:  # pragma: no cover
        import builtins as builtins_mod  # py3
        builtin_open_name = "open"

    originals = {
        "builtin_open_mod": builtins_mod,
        "builtin_open_name": builtin_open_name,
        "builtin_open": getattr(builtins_mod, builtin_open_name),
        "remove": os.remove,
        "unlink": os.unlink,
        "rename": os.rename,
        "rmdir": os.rmdir,
        "os_open": getattr(os, "open", None),
    }

    if shutil is not None:
        originals["move"] = shutil.move
        originals["rmtree"] = shutil.rmtree

    def fw_open(path, mode="r", *args, **kwargs):
        if _should_block_open(path, mode, allowed_write_root):
            _raise_blocked(path)
        return originals["builtin_open"](path, mode, *args, **kwargs)

    def fw_remove(path):
        if not is_path_within(path, allowed_write_root):
            _raise_blocked(path)
        return originals["remove"](path)

    def fw_unlink(path):
        if not is_path_within(path, allowed_write_root):
            _raise_blocked(path)
        return originals["unlink"](path)

    def fw_rename(src, dst):
        # Renames write to destination path.
        if (not is_path_within(src, allowed_write_root)) or (not is_path_within(dst, allowed_write_root)):
            _raise_blocked("%s -> %s" % (src, dst))
        return originals["rename"](src, dst)

    def fw_rmdir(path):
        if not is_path_within(path, allowed_write_root):
            _raise_blocked(path)
        return originals["rmdir"](path)

    def fw_os_open(path, flags, mode=0o777):
        if _should_block_os_open(path, flags, allowed_write_root):
            _raise_blocked(path)
        return originals["os_open"](path, flags, mode)

    def fw_move(src, dst):
        if (not is_path_within(src, allowed_write_root)) or (not is_path_within(dst, allowed_write_root)):
            _raise_blocked("%s -> %s" % (src, dst))
        return originals["move"](src, dst)

    def fw_rmtree(path, *args, **kwargs):
        if not is_path_within(path, allowed_write_root):
            _raise_blocked(path)
        return originals["rmtree"](path, *args, **kwargs)

    # Install patches.
    try:
        setattr(builtins_mod, builtin_open_name, fw_open)
    except Exception:
        pass

    os.remove = fw_remove
    os.unlink = fw_unlink
    os.rename = fw_rename
    os.rmdir = fw_rmdir

    # Best-effort os.open patch.
    if hasattr(os, "open") and originals.get("os_open") is not None:
        try:
            os.open = fw_os_open
        except Exception:
            pass

    if shutil is not None:
        shutil.move = fw_move
        shutil.rmtree = fw_rmtree

    _ORIGINALS = originals
    _FIREWALL_INSTALLED = True

    if verbose:
        try:
            print("Write firewall installed. Allowed root: %s" % (allowed_write_root,))
        except Exception:
            pass


