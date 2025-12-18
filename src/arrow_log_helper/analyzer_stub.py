from __future__ import absolute_import

"""
Stub analyzer for Arrow Log Helper.

IMPORTANT:
- Stdlib only
- Deterministic fake results (no filesystem scanning yet)
- Designed to let the GUI wiring be tested safely
"""


def _first_nonempty_line(text):
    if text is None:
        return ""
    for line in text.splitlines():
        if line.strip():
            return line.rstrip("\n")
    return ""


def _coerce_settings(settings):
    settings = settings or {}
    # Keep stable keys, even though the stub doesn't use them yet.
    return {
        "roots": settings.get("roots", []),
        "include_ext": settings.get("include_ext", [".py"]),
        "exclude_dirs": settings.get("exclude_dirs", []),
        "max_results": int(settings.get("max_results", 20) or 20),
    }


def _parse_log(text):
    """
    Very small heuristic parser for display purposes.
    This is NOT the real parser; it just makes the UI useful.
    """
    first = _first_nonempty_line(text)
    parsed = {
        "timestamp": "unknown",
        "machine": "unknown",
        "component": "unknown",
        "message": first or "(empty)",
    }

    # Heuristic: split on first ":" to get a component-ish prefix.
    if ":" in first:
        left, right = first.split(":", 1)
        parsed["message"] = right.strip() or parsed["message"]
        # Heuristic: "MACHINE COMPONENT" or "COMPONENT"
        parts = left.strip().split()
        if len(parts) >= 2:
            parsed["machine"] = parts[0]
            parsed["component"] = " ".join(parts[1:])
        elif len(parts) == 1 and parts[0]:
            parsed["component"] = parts[0]

    # Heuristic: if the line starts with something that looks like a timestamp, keep it.
    # (We don't validate; keep it stable and harmless.)
    if len(first) >= 19 and first[4] == "-" and first[7] == "-":
        parsed["timestamp"] = first[:19]

    return parsed


def analyze(text, settings=None):
    """
    Return deterministic fake results.

    Expected shape:
      {
        "parsed": {...},
        "matches": [
          {"score": 0.92, "component": "...", "path": "...", "line": 123,
           "matched_line": "...", "enclosure": "def ...", "block": "..."},
          ...
        ]
      }
    """
    settings = _coerce_settings(settings)
    parsed = _parse_log(text or "")

    # Deterministic pseudo-signal based on input content (still stable and safe).
    first = _first_nonempty_line(text or "")
    has_error = ("error" in first.lower()) if first else False
    component = parsed.get("component") or "unknown"

    base_path = "src/example/%s.py" % (component.replace(" ", "_").lower() or "module")

    matches = [
        {
            "score": 0.92 if has_error else 0.88,
            "component": component,
            "path": base_path,
            "line": 123,
            "matched_line": "raise RuntimeError('stub: simulated failure')",
            "enclosure": "def handle_log_event(event):",
            "block": "\n".join(
                [
                    "def handle_log_event(event):",
                    "    # stub enclosure; real extractor will populate this",
                    "    if event.get('level') == 'ERROR':",
                    "        raise RuntimeError('stub: simulated failure')",
                    "    return True",
                ]
            ),
        },
        {
            "score": 0.87,
            "component": component,
            "path": "src/example/search_index.py",
            "line": 45,
            "matched_line": "candidates = build_candidates(query)",
            "enclosure": "def build_candidates(query):",
            "block": "\n".join(
                [
                    "def build_candidates(query):",
                    "    # stub enclosure; real search will replace this",
                    "    candidates = []",
                    "    candidates.append(('path/to/file.py', 10))",
                    "    return candidates",
                ]
            ),
        },
        {
            "score": 0.63,
            "component": component,
            "path": "src/example/report.py",
            "line": 9,
            "matched_line": "return format_report(parsed, matches)",
            "enclosure": "def format_report(parsed, matches):",
            "block": "\n".join(
                [
                    "def format_report(parsed, matches):",
                    "    # stub enclosure; real reporter will replace this",
                    "    lines = []",
                    "    lines.append('Parsed: %r' % (parsed,))",
                    "    lines.append('Matches: %d' % (len(matches),))",
                    "    return '\\n'.join(lines)",
                ]
            ),
        },
    ]

    # Obey max_results in a harmless way.
    max_results = settings.get("max_results", 20)
    try:
        max_results = int(max_results)
    except Exception:
        max_results = 20
    if max_results < 1:
        max_results = 1
    matches = matches[:max_results]

    return {"parsed": parsed, "matches": matches}


