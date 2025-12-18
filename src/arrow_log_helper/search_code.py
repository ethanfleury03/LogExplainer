from __future__ import absolute_import

import os


DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_MAX_RESULTS = 10


def safe_walk_files(
    roots,
    include_exts,
    exclude_dir_names,
    follow_symlinks=False,
    max_file_bytes=DEFAULT_MAX_FILE_BYTES,
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
                    continue
                full_d = os.path.join(dirpath, d)
                if not follow_symlinks:
                    try:
                        if os.path.islink(full_d):
                            continue
                    except Exception:
                        # If islink fails, be conservative: keep it out.
                        continue
                kept.append(d)
            dirnames[:] = kept

            for fn in filenames:
                path = os.path.join(dirpath, fn)

                if not follow_symlinks:
                    try:
                        if os.path.islink(path):
                            continue
                    except Exception:
                        continue

                # Regular file + size guard.
                try:
                    st = os.stat(path)
                except Exception:
                    continue
                try:
                    if not os.path.isfile(path):
                        continue
                except Exception:
                    continue
                try:
                    if st.st_size > max_file_bytes:
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


def iter_lines(path, case_insensitive=False):
    """
    Yield (line_no, line_text) from a file.

    - Reads bytes from disk (rb)
    - Decodes lossy for matching/display
    """
    try:
        f = open(path, "rb")
    except Exception:
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

    results = []
    seen = set()

    # Precompute file list once to keep deterministic iteration across passes.
    files = list(
        safe_walk_files(
            roots=roots,
            include_exts=include_exts,
            exclude_dir_names=exclude_dir_names,
            follow_symlinks=follow_symlinks,
            max_file_bytes=max_file_bytes,
        )
    )

    def run_pass(match_type, key=None, tokens_=None):
        for path in files:
            for line_no, line_text in iter_lines(path, case_insensitive=case_insensitive):
                ok = False
                if match_type in ("exact", "normalized"):
                    ok = match_line(line_text, key, case_insensitive=case_insensitive)
                elif match_type == "tokens":
                    ok = tokens_match(line_text, tokens_, case_insensitive=case_insensitive)
                if not ok:
                    continue
                score = compute_score(match_type, line_text, component, case_insensitive=case_insensitive)
                _add_match(results, seen, path, line_no, line_text, match_type, score)
                if len(results) >= max_results:
                    return

    # Pass 1: exact
    run_pass("exact", key=key_exact)
    if len(results) < max_results:
        # Pass 2: normalized
        run_pass("normalized", key=key_normalized)
    if len(results) < max_results:
        # Pass 3: tokens
        run_pass("tokens", tokens_=tokens or [])

    results.sort(key=lambda m: (-m.get("score", 0.0), m.get("path", ""), m.get("line_no", 0)))
    return results[:max_results]


