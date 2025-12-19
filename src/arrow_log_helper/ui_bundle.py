from __future__ import absolute_import, print_function

import json
import os


def _make_json_serializable(obj):
    """Convert obj to JSON-serializable form (handles sets, bytes, unicode)."""
    if obj is None:
        return None
    if isinstance(obj, (bool, int, float)):
        return obj
    # Handle string types (str in py3, str/unicode in py2)
    try:
        # Check if unicode type exists (Python 2)
        unicode_type = unicode  # noqa: F821
        if isinstance(obj, (str, unicode_type)):
            try:
                return str(obj)
            except Exception:
                return repr(obj)
    except NameError:
        # Python 3: unicode doesn't exist, all strings are str
        if isinstance(obj, str):
            try:
                return str(obj)
            except Exception:
                return repr(obj)
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", "replace")
        except Exception:
            return repr(obj)
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(x) for x in obj]
    if isinstance(obj, dict):
        return dict((_make_json_serializable(k), _make_json_serializable(v)) for k, v in obj.items())
    if isinstance(obj, set):
        return sorted([_make_json_serializable(x) for x in obj])
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def _compute_confidence_percent(score):
    """Convert score (0.0-1.0) to integer percent (0-100)."""
    try:
        score = float(score)
        if score < 0.0:
            score = 0.0
        if score > 1.0:
            score = 1.0
        return int(round(score * 100))
    except Exception:
        return 0


def _compute_location_short(path, line_no):
    """Format as basename(path):line."""
    try:
        base = os.path.basename(str(path))
        line = int(line_no)
        return "%s:%d" % (base, line)
    except Exception:
        return "%s:%s" % (str(path), str(line_no))


def _compute_enclosure_display_name(enclosure_type, name, signature):
    """Format enclosure as 'def name(args)' or 'class Name' or '<none>'."""
    if signature:
        return signature
    if enclosure_type in ("def", "async_def") and name:
        prefix = "async def " if enclosure_type == "async_def" else "def "
        return "%s%s(...)" % (prefix, name,)
    if enclosure_type == "class" and name:
        return "class %s" % (name,)
    if enclosure_type == "module":
        return "<module>"
    if enclosure_type == "window":
        return "<context window>"
    return "<none>"


def _generate_summary_text(match, parsed, search_message):
    """Generate deterministic summary template."""
    lines = []
    
    # Function/Enclosure
    enclosure_type = match.get("enclosure_type") or "none"
    name = match.get("name")
    signature = match.get("signature")
    display_name = _compute_enclosure_display_name(enclosure_type, name, signature)
    lines.append("Function/Enclosure: %s" % (display_name,))
    
    # Match info
    match_type = match.get("match_type") or "unknown"
    score = match.get("score", 0.0)
    confidence = _compute_confidence_percent(score)
    path = match.get("path", "?")
    line_no = match.get("line_no", "?")
    location = _compute_location_short(path, line_no)
    lines.append("Match info: %s, %d%%, %s" % (match_type, confidence, location))
    
    # Log literal key (search_message)
    if search_message:
        lines.append("Log literal key: %s" % (search_message[:60] + "..." if len(search_message) > 60 else search_message,))
    
    # Component token
    component = match.get("component") or (parsed.get("component") if isinstance(parsed, dict) else None)
    if component:
        lines.append("Component: %s" % (component,))
    
    return "\n".join(lines)


def build_ui_bundle(analysis_result, selected_match_index):
    """
    Transform analyzer output into UI-friendly format.
    
    Args:
        analysis_result: dict with keys: selected_line, parsed, search_message, matches, scan_stats
        selected_match_index: int index into matches list, or None if no selection
    
    Returns:
        dict with keys: input, parsed, scan, matches, selected
    """
    if not analysis_result:
        analysis_result = {}
    
    # Extract base fields
    input_data = {
        "selected_line": analysis_result.get("selected_line", ""),
        "search_message": analysis_result.get("search_message", ""),
    }
    
    parsed = analysis_result.get("parsed") or {}
    scan_stats = analysis_result.get("scan_stats") or {}
    matches_raw = analysis_result.get("matches") or []
    
    # Process matches list with computed fields
    matches = []
    for m in matches_raw:
        match_dict = dict(m)
        
        # Compute additional fields
        score = match_dict.get("score", 0.0)
        match_dict["confidence_percent"] = _compute_confidence_percent(score)
        
        path = match_dict.get("path", "")
        line_no = match_dict.get("line_no", 0)
        match_dict["location_short"] = _compute_location_short(path, line_no)
        
        enclosure_type = match_dict.get("enclosure_type")
        name = match_dict.get("name")
        signature = match_dict.get("signature")
        match_dict["enclosure_display_name"] = _compute_enclosure_display_name(enclosure_type, name, signature)
        
        # Generate summary for each match
        search_message = analysis_result.get("search_message", "")
        match_dict["summary_text"] = _generate_summary_text(match_dict, parsed, search_message)
        
        matches.append(match_dict)
    
    # Sort matches by score descending (already sorted by analyzer, but ensure)
    matches.sort(key=lambda m: (-m.get("score", 0.0), m.get("path", ""), m.get("line_no", 0)))
    
    # Select the chosen match
    selected = None
    if selected_match_index is not None:
        try:
            idx = int(selected_match_index)
            if 0 <= idx < len(matches):
                selected = dict(matches[idx])
        except Exception:
            pass
    
    # Build scan stats dict (normalize)
    scan = {}
    for k in (
        "files_scanned",
        "files_skipped_excluded_dir",
        "files_skipped_symlink",
        "files_skipped_too_big",
        "files_skipped_unreadable",
        "hits_found",
        "elapsed_seconds",
        "stopped_reason",
        "notes",
    ):
        if k in scan_stats:
            scan[k] = scan_stats[k]
    
    # Build bundle
    bundle = {
        "input": _make_json_serializable(input_data),
        "parsed": _make_json_serializable(parsed),
        "scan": _make_json_serializable(scan),
        "matches": _make_json_serializable(matches),
        "selected": _make_json_serializable(selected),
    }
    
    return bundle


def pretty_json(obj):
    """
    Pretty-print JSON for display/export.
    
    Args:
        obj: any JSON-serializable object
    
    Returns:
        str: pretty-printed JSON
    """
    try:
        # Ensure serializable
        serializable = _make_json_serializable(obj)
        # Pretty print
        txt = json.dumps(serializable, indent=2, sort_keys=True)
        if not txt.endswith("\n"):
            txt += "\n"
        return txt
    except Exception as e:
        # Fallback: return error message
        return "Error formatting JSON: %s\n" % (str(e),)

