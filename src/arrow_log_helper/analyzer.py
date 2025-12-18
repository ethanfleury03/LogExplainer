from __future__ import absolute_import

from arrow_log_helper import extract_enclosure
from arrow_log_helper import parse_log
from arrow_log_helper import search_code
from arrow_log_helper import config_defaults


def _coerce_settings(settings, defaults_module=None):
    settings = settings or {}
    defaults = defaults_module or config_defaults

    def _d(name, fallback):
        if defaults is None:
            return fallback
        return getattr(defaults, name, fallback)

    roots = settings.get("roots", None)
    if roots is None:
        roots = list(_d("DEFAULT_ROOTS", []))
    include_ext = settings.get("include_ext", None)
    if include_ext is None:
        include_ext = list(_d("DEFAULT_INCLUDE_EXT", [".py"]))
    exclude_dirs = settings.get("exclude_dirs", None)
    if exclude_dirs is None:
        exclude_dirs = list(_d("DEFAULT_EXCLUDE_DIRS", []))

    max_results = settings.get("max_results", _d("DEFAULT_MAX_RESULTS", search_code.DEFAULT_MAX_RESULTS))
    max_file_bytes = settings.get("max_file_bytes", _d("DEFAULT_MAX_FILE_BYTES", search_code.DEFAULT_MAX_FILE_BYTES))
    max_seconds = settings.get("max_seconds", _d("DEFAULT_MAX_SECONDS", None))
    max_files_scanned = settings.get("max_files_scanned", _d("DEFAULT_MAX_FILES_SCANNED", None))
    context_fallback = settings.get("context_fallback", 50)
    progress_every_n_files = settings.get(
        "progress_every_n_files", _d("DEFAULT_PROGRESS_EVERY_N_FILES", 100)
    )
    case_insensitive = bool(settings.get("case_insensitive", False))
    follow_symlinks = bool(settings.get("follow_symlinks", False))

    # max_results can be None => unlimited (real-machine mode)
    if max_results is not None:
        try:
            max_results = int(max_results)
        except Exception:
            max_results = search_code.DEFAULT_MAX_RESULTS
    try:
        max_file_bytes = int(max_file_bytes)
    except Exception:
        max_file_bytes = search_code.DEFAULT_MAX_FILE_BYTES
    try:
        if max_seconds is not None:
            max_seconds = float(max_seconds)
    except Exception:
        max_seconds = None
    try:
        if max_files_scanned is not None:
            max_files_scanned = int(max_files_scanned)
    except Exception:
        max_files_scanned = None
    try:
        progress_every_n_files = int(progress_every_n_files)
    except Exception:
        progress_every_n_files = 100
    try:
        context_fallback = int(context_fallback)
    except Exception:
        context_fallback = 50

    return {
        "roots": roots,
        "include_ext": include_ext,
        "exclude_dirs": exclude_dirs,
        "max_results": max_results,
        "max_file_bytes": max_file_bytes,
        "max_seconds": max_seconds,
        "max_files_scanned": max_files_scanned,
        "progress_every_n_files": progress_every_n_files,
        "context_fallback": context_fallback,
        "case_insensitive": case_insensitive,
        "follow_symlinks": follow_symlinks,
    }


def analyze(text, settings=None, progress_cb=None, defaults_module=None):
    """
    Real-machine mode analysis pipeline (read-only):
      parse_log -> exact message search -> extract enclosure -> signature/context preview
    """
    s = _coerce_settings(settings, defaults_module=defaults_module)

    parsed_all = parse_log.analyze_pasted_text(text or "", normalize_numbers=False)

    # Structured "parsed" section for UI/backends.
    parsed = {
        "timestamp": parsed_all.get("timestamp"),
        "host_or_serial": parsed_all.get("host_or_serial"),
        "process": parsed_all.get("process"),
        "level": parsed_all.get("level"),
        "thread": parsed_all.get("thread"),
        "component": parsed_all.get("component"),
        "message": parsed_all.get("message") or "",
    }

    message = (parsed_all.get("search_message") or "").strip()

    matches = []
    scan_stats = search_code.new_scan_stats()
    if not message:
        scan_stats["notes"] = "Empty search_message; no search performed."
        return {
            "selected_line": parsed_all.get("selected_line", ""),
            "parsed": parsed,
            "search_message": message,
            "matches": [],
            "scan_stats": scan_stats,
        }

    # Force source-only scanning (skip pyc/pyo).
    include_exts = [".py"]

    matches, scan_stats = search_code.search_message_exact_in_roots(
        roots=s.get("roots"),
        message=message,
        include_exts=include_exts,
        exclude_dir_names=s.get("exclude_dirs"),
        case_insensitive=s.get("case_insensitive", False),
        follow_symlinks=s.get("follow_symlinks", False),
        max_file_bytes=s.get("max_file_bytes"),
        max_seconds=s.get("max_seconds"),
        max_files_scanned=s.get("max_files_scanned"),
        progress_cb=progress_cb,
        progress_every_n_files=s.get("progress_every_n_files", 100),
        max_results=s.get("max_results"),
        component=parsed_all.get("component"),
    )

    # Enrich each match with signature only (or context preview if no def/class).
    enriched = []
    for m in matches:
        try:
            enc = extract_enclosure.extract_enclosure(
                m.get("path"), m.get("line_no"), context_fallback=s.get("context_fallback", 50)
            )
        except Exception:
            enc = {
                "enclosure_type": "none",
                "name": None,
                "start_line": m.get("line_no", 1),
                "end_line": m.get("line_no", 1),
                "block": "",
                "notes": "extract_enclosure failed",
            }

        signature = extract_enclosure.extract_signature_only(enc)

        merged = dict(m)
        merged["enclosure_type"] = enc.get("enclosure_type")
        merged["name"] = enc.get("name")
        merged["start_line"] = enc.get("start_line")
        merged["end_line"] = enc.get("end_line")
        merged["signature"] = signature
        if signature is None and enc.get("enclosure_type") == "none":
            merged["context_preview"] = enc.get("block")
        else:
            merged["context_preview"] = None
        if enc.get("notes"):
            merged["notes"] = enc.get("notes")
        enriched.append(merged)

    return {
        "selected_line": parsed_all.get("selected_line", ""),
        "parsed": parsed,
        "search_message": message,
        "matches": enriched,
        "scan_stats": scan_stats,
    }


