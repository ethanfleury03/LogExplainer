from __future__ import absolute_import

import os
import time


DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_MAX_RESULTS = 10


def new_scan_stats():
    return {
        "files_scanned": 0,
        "files_skipped_excluded_dir": 0,
        "files_skipped_symlink": 0,
        "files_skipped_too_big": 0,
        "files_skipped_unreadable": 0,
        "hits_found": 0,
        "elapsed_seconds": 0.0,
        "stopped_reason": None,
    }


def search_message_exact_in_roots(
    roots,
    message,
    include_exts,
    exclude_dir_names,
    case_insensitive=False,
    follow_symlinks=False,
    max_file_bytes=DEFAULT_MAX_FILE_BYTES,
    max_results=None,
    progress_cb=None,
    progress_every_n_files=100,
    max_seconds=None,
    max_files_scanned=None,
    component=None,
):
    """
    Single-pass search for message substring in source lines.

    - match_type always "exact_message"
    - If max_results is None: do NOT stop based on results count
    - Still enforces max_seconds/max_files_scanned if provided
    - Returns (results, stats)
    """
    stats = new_scan_stats()
    started = time.time()

    # Defensive normalization
    message = "" if message is None else message
    try:
        message = str(message)
    except Exception:
        message = repr(message)
    message = message.strip()

    include_exts = include_exts or [".py"]
    # Skip compiled artifacts even if caller accidentally includes broad ext patterns.
    include_exts = [e for e in include_exts if e not in (".pyc", ".pyo")]

    try:
        progress_every_n_files = int(progress_every_n_files)
    except Exception:
        progress_every_n_files = 100
    if progress_every_n_files < 1:
        progress_every_n_files = 1

    def _elapsed():
        try:
            return float(time.time() - started)
        except Exception:
            return 0.0

    def _maybe_progress(force=False):
        stats["elapsed_seconds"] = _elapsed()
        if progress_cb is None:
            return
        if force or (stats["files_scanned"] % progress_every_n_files == 0):
            try:
                progress_cb(dict(stats))
            except Exception:
                pass

    def _should_stop_before_file():
        stats["elapsed_seconds"] = _elapsed()
        if max_seconds is not None:
            try:
                if stats["elapsed_seconds"] >= float(max_seconds):
                    stats["stopped_reason"] = "max_seconds"
                    return True
            except Exception:
                pass
        if max_files_scanned is not None:
            try:
                if stats["files_scanned"] >= int(max_files_scanned):
                    stats["stopped_reason"] = "max_files"
                    return True
            except Exception:
                pass
        if max_results is not None:
            try:
                if len(results) >= int(max_results):
                    stats["stopped_reason"] = "max_results"
                    return True
            except Exception:
                pass
        return False

    def _score_for_line(line_text):
        score = 1.0
        if component and line_text:
            try:
                if case_insensitive:
                    if str(component).lower() in str(line_text).lower():
                        score += 0.1
                else:
                    if str(component) in str(line_text):
                        score += 0.1
            except Exception:
                pass
        if score > 1.0:
            score = 1.0
        return float(score)

    results = []
    seen = set()

    _maybe_progress(force=True)

    if not message:
        stats["elapsed_seconds"] = _elapsed()
        _maybe_progress(force=True)
        return (results, stats)

    for path in safe_walk_files(
        roots=roots,
        include_exts=include_exts,
        exclude_dir_names=exclude_dir_names,
        follow_symlinks=follow_symlinks,
        max_file_bytes=max_file_bytes,
        stats=stats,
    ):
        if _should_stop_before_file():
            break

        for line_no, line_text in iter_lines(path, case_insensitive=case_insensitive, stats=stats):
            if match_line(line_text, message, case_insensitive=case_insensitive):
                before = len(results)
                _add_match(results, seen, path, line_no, line_text, "exact_message", _score_for_line(line_text))
                after = len(results)
                if after > before:
                    try:
                        stats["hits_found"] += 1
                    except Exception:
                        pass
                if max_results is not None:
                    try:
                        if len(results) >= int(max_results):
                            stats["stopped_reason"] = "max_results"
                            break
                    except Exception:
                        pass

        stats["files_scanned"] += 1
        _maybe_progress(force=False)

        if stats.get("stopped_reason") == "max_results":
            break

    stats["elapsed_seconds"] = _elapsed()
    _maybe_progress(force=True)

    results.sort(key=lambda m: (-m.get("score", 0.0), m.get("path", ""), m.get("line_no", 0)))
    if max_results is not None:
        try:
            return (results[: int(max_results)], stats)
        except Exception:
            pass
    return (results, stats)


def safe_walk_files(
    roots,
    include_exts,
    exclude_dir_names,
    follow_symlinks=False,
    max_file_bytes=DEFAULT_MAX_FILE_BYTES,
    stats=None,
):
    """
    Read-only file walker.

    - Excludes directories by NAME (not path)
    - Does not follow symlink dirs/files by default
    - Filters by extension
    - Skips large files
    """
    roots = roots or []
    include_exts = include_exts or []
    exclude_dir_names = set(exclude_dir_names or [])

    include_exts_l = [e.lower() for e in include_exts]

    for root in roots:
        if not root:
            continue
        try:
            root_abs = os.path.abspath(root)
        except Exception:
            root_abs = root
        if not os.path.isdir(root_abs):
            continue

        for dirpath, dirnames, filenames in os.walk(root_abs, topdown=True):
            # Exclude by directory name (in-place).
            kept = []
            for d in dirnames:
                if d in exclude_dir_names:
                    # Directory-level count only (file-level would be expensive/inaccurate).
                    if stats is not None:
                        try:
                            stats["files_skipped_excluded_dir"] += 1
                        except Exception:
                            pass
                    continue
                full_d = os.path.join(dirpath, d)
                if not follow_symlinks:
                    try:
                        if os.path.islink(full_d):
                            if stats is not None:
                                try:
                                    stats["files_skipped_symlink"] += 1
                                except Exception:
                                    pass
                            continue
                    except Exception:
                        # If islink fails, be conservative: keep it out.
                        if stats is not None:
                            try:
                                stats["files_skipped_symlink"] += 1
                            except Exception:
                                pass
                        continue
                kept.append(d)
            dirnames[:] = kept

            for fn in filenames:
                path = os.path.join(dirpath, fn)

                if not follow_symlinks:
                    try:
                        if os.path.islink(path):
                            if stats is not None:
                                try:
                                    stats["files_skipped_symlink"] += 1
                                except Exception:
                                    pass
                            continue
                    except Exception:
                        if stats is not None:
                            try:
                                stats["files_skipped_symlink"] += 1
                            except Exception:
                                pass
                        continue

                # Regular file + size guard.
                try:
                    st = os.stat(path)
                except Exception:
                    if stats is not None:
                        try:
                            stats["files_skipped_unreadable"] += 1
                        except Exception:
                            pass
                    continue
                try:
                    if not os.path.isfile(path):
                        continue
                except Exception:
                    continue
                try:
                    if st.st_size > max_file_bytes:
                        if stats is not None:
                            try:
                                stats["files_skipped_too_big"] += 1
                            except Exception:
                                pass
                        continue
                except Exception:
                    continue

                # Extension filter.
                p_l = path.lower()
                if include_exts_l:
                    ok = False
                    for ext in include_exts_l:
                        if p_l.endswith(ext):
                            ok = True
                            break
                    if not ok:
                        continue

                yield path


def _decode_lossy(b):
    # b is expected to be a bytes/str from a binary file read.
    try:
        return b.decode("utf-8")
    except Exception:
        try:
            return b.decode("utf-8", "replace")
        except Exception:
            try:
                return b.decode("latin-1", "replace")
            except Exception:
                # Last resort: best-effort stringification.
                try:
                    return str(b)
                except Exception:
                    return repr(b)


def iter_lines(path, case_insensitive=False, stats=None):
    """
    Yield (line_no, line_text) from a file.

    - Reads bytes from disk (rb)
    - Decodes lossy for matching/display
    """
    try:
        f = open(path, "rb")
    except Exception:
        if stats is not None:
            try:
                stats["files_skipped_unreadable"] += 1
            except Exception:
                pass
        return

    try:
        line_no = 0
        for raw in f:
            line_no += 1
            try:
                text = _decode_lossy(raw)
            except Exception:
                continue
            # Normalize newlines for matching/display.
            text = text.rstrip("\r\n")
            yield (line_no, text)
    finally:
        try:
            f.close()
        except Exception:
            pass


def match_line(line_text, key, case_insensitive):
    if not key:
        return False
    if line_text is None:
        return False
    if case_insensitive:
        return key.lower() in line_text.lower()
    return key in line_text


def tokens_match(line_text, tokens, case_insensitive):
    if not tokens or len(tokens) < 2:
        return False
    if line_text is None:
        return False
    hay = line_text
    if case_insensitive:
        hay = hay.lower()
    for t in tokens:
        if not t:
            continue
        needle = t.lower() if case_insensitive else t
        if needle not in hay:
            return False
    return True


def compute_score(match_type, line_text, component, case_insensitive):
    base = 0.0
    if match_type == "exact":
        base = 1.0
    elif match_type == "normalized":
        base = 0.8
    elif match_type == "tokens":
        base = 0.6
    else:
        base = 0.0

    boost = 0.0
    if component and line_text:
        if case_insensitive:
            if component.lower() in line_text.lower():
                boost = 0.1
        else:
            if component in line_text:
                boost = 0.1

    score = base + boost
    if score > 1.0:
        score = 1.0
    return float(score)


def _add_match(results, seen, path, line_no, line_text, match_type, score):
    key = (path, int(line_no))
    if key in seen:
        return
    seen.add(key)
    results.append(
        {
            "path": path,
            "line_no": int(line_no),
            "line_text": line_text,
            "match_type": match_type,
            "score": float(score),
        }
    )


def search_in_roots(
    roots,
    key_exact,
    key_normalized,
    tokens,
    component,
    include_exts,
    exclude_dir_names,
    case_insensitive=False,
    max_results=DEFAULT_MAX_RESULTS,
    follow_symlinks=False,
    max_file_bytes=DEFAULT_MAX_FILE_BYTES,
    max_seconds=None,
    max_files_scanned=None,
    progress_cb=None,
    progress_every_n_files=100,
):
    """
    Two/three pass search:
      1) exact (key_exact)
      2) normalized (key_normalized)
      3) tokens (ALL tokens must appear; requires >=2 tokens)
    """
    try:
        max_results = int(max_results)
    except Exception:
        max_results = DEFAULT_MAX_RESULTS
    if max_results < 1:
        max_results = 1

    stats = new_scan_stats()
    started = time.time()

    try:
        progress_every_n_files = int(progress_every_n_files)
    except Exception:
        progress_every_n_files = 100
    if progress_every_n_files < 1:
        progress_every_n_files = 1

    def _elapsed():
        try:
            return float(time.time() - started)
        except Exception:
            return 0.0

    def _maybe_progress(force=False):
        stats["elapsed_seconds"] = _elapsed()
        if progress_cb is None:
            return
        if force or (stats["files_scanned"] % progress_every_n_files == 0):
            try:
                progress_cb(dict(stats))
            except Exception:
                pass

    def _should_stop_before_file():
        stats["elapsed_seconds"] = _elapsed()
        if max_seconds is not None:
            try:
                if stats["elapsed_seconds"] >= float(max_seconds):
                    stats["stopped_reason"] = "max_seconds"
                    return True
            except Exception:
                pass
        if max_files_scanned is not None:
            try:
                if stats["files_scanned"] >= int(max_files_scanned):
                    stats["stopped_reason"] = "max_files"
                    return True
            except Exception:
                pass
        if len(results) >= max_results:
            stats["stopped_reason"] = "max_results"
            return True
        return False

    results = []
    seen = set()
    files_pass1 = []

    _maybe_progress(force=True)

    def run_pass(match_type, file_iter, key=None, tokens_=None):
        for path in file_iter:
            if _should_stop_before_file():
                return

            # Scan the file.
            for line_no, line_text in iter_lines(path, case_insensitive=case_insensitive, stats=stats):
                ok = False
                if match_type in ("exact", "normalized"):
                    ok = match_line(line_text, key, case_insensitive=case_insensitive)
                elif match_type == "tokens":
                    ok = tokens_match(line_text, tokens_, case_insensitive=case_insensitive)
                if not ok:
                    continue

                score = compute_score(match_type, line_text, component, case_insensitive=case_insensitive)

                before = len(results)
                _add_match(results, seen, path, line_no, line_text, match_type, score)
                after = len(results)
                if after > before:
                    try:
                        stats["hits_found"] += 1
                    except Exception:
                        pass
                if after >= max_results:
                    stats["stopped_reason"] = "max_results"
                    break

            stats["files_scanned"] += 1
            _maybe_progress(force=False)

            if stats.get("stopped_reason") == "max_results":
                return

    # Pass 1: exact
    def _iter_files_pass1():
        for p in safe_walk_files(
            roots=roots,
            include_exts=include_exts,
            exclude_dir_names=exclude_dir_names,
            follow_symlinks=follow_symlinks,
            max_file_bytes=max_file_bytes,
            stats=stats,
        ):
            files_pass1.append(p)
            yield p

    run_pass("exact", file_iter=_iter_files_pass1(), key=key_exact)
    if stats.get("stopped_reason") is None and len(results) < max_results:
        run_pass("normalized", file_iter=files_pass1, key=key_normalized)
    if stats.get("stopped_reason") is None and len(results) < max_results:
        run_pass("tokens", file_iter=files_pass1, tokens_=tokens or [])

    stats["elapsed_seconds"] = _elapsed()
    _maybe_progress(force=True)

    results.sort(key=lambda m: (-m.get("score", 0.0), m.get("path", ""), m.get("line_no", 0)))
    return (results[:max_results], stats)


