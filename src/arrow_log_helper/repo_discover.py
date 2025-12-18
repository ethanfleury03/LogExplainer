from __future__ import absolute_import, print_function

import os
try:
    from collections import deque
except Exception:
    deque = None


MARKER_FILES = [
    "setup.py",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "pom.xml",
    "build.gradle",
    "CMakeLists.txt",
    "Makefile",
    ".git",
]

CODE_EXTS = [".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp", ".sh"]

DEFAULT_EXCLUDE_DIRS = [
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


def _is_drive_root(p):
    # Windows drive roots like C:\ or C:/
    try:
        p = os.path.abspath(p)
    except Exception:
        return False
    if len(p) == 3 and p[1] == ":" and p[2] in ("\\", "/"):
        return True
    return False


def safe_is_massive_root(path):
    try:
        p = os.path.abspath(path)
    except Exception:
        p = path
    # POSIX root
    if p == os.path.abspath(os.sep):
        return True
    # Windows drive root
    if _is_drive_root(p):
        return True
    return False


def _has_git_marker(dirpath, entries):
    if ".git" not in entries:
        return False
    try:
        return os.path.isdir(os.path.join(dirpath, ".git"))
    except Exception:
        return False


def _count_markers(dirpath, entries):
    markers = []
    for m in MARKER_FILES:
        if m == ".git":
            if ".git" in entries and os.path.isdir(os.path.join(dirpath, ".git")):
                markers.append(".git")
            continue
        if m in entries:
            p = os.path.join(dirpath, m)
            try:
                if os.path.isfile(p):
                    markers.append(m)
            except Exception:
                pass
    return markers


def _count_code_files_here(dirpath, entries):
    exts = set([e.lower() for e in CODE_EXTS])
    n_code = 0
    n_total_files = 0
    for name in entries:
        p = os.path.join(dirpath, name)
        try:
            if os.path.isfile(p):
                n_total_files += 1
                _, ext = os.path.splitext(name)
                if ext.lower() in exts:
                    n_code += 1
        except Exception:
            continue
    return n_code, n_total_files


def discover_candidates(
    base_paths,
    max_depth=6,
    exclude_dir_names=None,
    follow_symlinks=False,
    progress_cb=None,
):
    """
    Breadth-first discovery of likely code roots.
    Read-only; never writes.
    """
    base_paths = base_paths or []
    try:
        max_depth = int(max_depth)
    except Exception:
        max_depth = 6
    if max_depth < 0:
        max_depth = 0

    exclude = set(exclude_dir_names or DEFAULT_EXCLUDE_DIRS)

    if deque is None:
        # Fallback: poor-man queue
        q = []
        def push(x): q.append(x)
        def pop0(): return q.pop(0)
        def empty(): return len(q) == 0
    else:
        q = deque()
        def push(x): q.append(x)
        def pop0(): return q.popleft()
        def empty(): return len(q) == 0

    visited = set()
    candidates = []
    visited_count = 0

    def maybe_progress(current_path):
        if progress_cb is None:
            return
        if visited_count == 1 or (visited_count % 50 == 0):
            try:
                progress_cb({"dirs_visited": visited_count, "current_dir": current_path})
            except Exception:
                pass

    for b in base_paths:
        if not b:
            continue
        try:
            b_abs = os.path.abspath(b)
        except Exception:
            b_abs = b
        if not os.path.isdir(b_abs):
            continue
        push((b_abs, 0))

    while not empty():
        dirpath, depth = pop0()
        if dirpath in visited:
            continue
        visited.add(dirpath)

        visited_count += 1
        maybe_progress(dirpath)

        try:
            entries = os.listdir(dirpath)
        except Exception:
            continue

        git = _has_git_marker(dirpath, entries)
        markers = _count_markers(dirpath, entries)
        marker_hits = len(markers)
        code_here, total_here = _count_code_files_here(dirpath, entries)

        score = 0
        if git:
            score += 100
        score += 20 * marker_hits
        try:
            score += min(int(code_here), 50)
        except Exception:
            pass

        if score > 0:
            candidates.append(
                {
                    "path": dirpath,
                    "score": int(score),
                    "git": bool(git),
                    "markers": markers,
                    "code_files_here": int(code_here),
                    "total_files_here": int(total_here),
                }
            )

        if depth >= max_depth:
            continue

        # Enqueue children (directories only), excluding by name.
        for name in sorted(entries):
            if name in exclude:
                continue
            p = os.path.join(dirpath, name)
            try:
                if not os.path.isdir(p):
                    continue
            except Exception:
                continue
            if not follow_symlinks:
                try:
                    if os.path.islink(p):
                        continue
                except Exception:
                    continue
            push((p, depth + 1))

    candidates.sort(key=lambda c: (-c.get("score", 0), c.get("path", "")))
    return candidates[:200]


