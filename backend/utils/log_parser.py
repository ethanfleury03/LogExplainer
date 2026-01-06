"""
Log parser for Kareela/Gymea route detection and query normalization.

This module provides best-effort parsing of log lines to extract:
- Route (kareela/gymea/unknown)
- Normalized query text for search
- Optional debug fields (severity, tag, component)
"""

import re
import logging
from typing import Dict, Optional, Any, Tuple

logger = logging.getLogger(__name__)


def parse_log_line(log_line: str) -> Dict[str, Any]:
    """
    Parse log line to extract route, payload, and normalized query text.
    
    Returns dict with:
    - route: "kareela" | "gymea" | "unknown"
    - confidence: float 0..1
    - payload: string (everything after route prefix, or full line)
    - query_text: string (normalized for search)
    - severity: string | None (if extractable)
    - tag: string | None (if extractable)
    - component: string | None (if extractable)
    
    NEVER fails - always returns a dict, even if parsing fails.
    """
    # Convert to string if not already
    if not isinstance(log_line, str):
        if log_line is None:
            return _unknown_result("")
        try:
            log_line = str(log_line)
        except Exception:
            return _unknown_result("")
    
    if not log_line:
        return _unknown_result("")
    
    log_line = log_line.strip()
    if not log_line:
        return _unknown_result("")
    
    # Try to detect route from prefix patterns
    route, confidence, payload = _detect_route(log_line)
    
    # Strip app prefix and extract optional debug fields
    stripped_payload, severity, tag, component = _strip_app_prefix(payload)
    
    # Normalize query text from stripped payload
    query_text = _normalize_query_text(stripped_payload, component)
    
    result = {
        "route": route,
        "confidence": confidence,
        "payload": payload,
        "query_text": query_text,
        "severity": severity,
        "tag": tag,
        "component": component,
    }
    
    logger.debug(
        f"Parsed log: route={route}, confidence={confidence:.2f}, "
        f"query_text='{query_text[:50]}...'"
    )
    
    return result


def _detect_route(log_line: str) -> Tuple[str, float, str]:
    """
    Detect route from log line prefix.
    
    Returns (route, confidence, payload)
    """
    # Pattern: timestamp host Kareela\d*: ... or Gymea\d*: ...
    # Examples:
    # "2026-01-06T09:47:26.310054+11:00 RS20300529 Kareela0: <E> [#4] MMCap: ..."
    # "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: ..."
    
    # Look for "Kareela\d*:" or "Gymea\d*:" (case-insensitive)
    kareela_match = re.search(r'\bKareela\d*\s*:\s*', log_line, re.IGNORECASE)
    gymea_match = re.search(r'\bGymea\d*\s*:\s*', log_line, re.IGNORECASE)
    
    if kareela_match:
        payload = log_line[kareela_match.end():].strip()
        return ("kareela", 0.95, payload)
    
    if gymea_match:
        payload = log_line[gymea_match.end():].strip()
        return ("gymea", 0.95, payload)
    
    # Fallback: check for route keywords in the line (lower confidence)
    log_lower = log_line.lower()
    if "kareela" in log_lower and "gymea" not in log_lower:
        # Extract payload after timestamp/host if present
        payload = _strip_timestamp_prefix(log_line)
        return ("kareela", 0.6, payload)
    
    if "gymea" in log_lower and "kareela" not in log_lower:
        payload = _strip_timestamp_prefix(log_line)
        return ("gymea", 0.6, payload)
    
    # Unknown route
    payload = _strip_timestamp_prefix(log_line)
    return ("unknown", 0.0, payload)


def _strip_timestamp_prefix(log_line: str) -> str:
    """
    Strip timestamp and host prefix if present.
    Pattern: "2025-12-19T05:22:06.895453+11:00 RS20300529 ..."
    """
    # Match ISO timestamp + host pattern
    timestamp_pattern = r'^\d{4}-\d{2}-\d{2}T[\d:\.+-]+\s+\S+\s+'
    match = re.match(timestamp_pattern, log_line)
    if match:
        return log_line[match.end():].strip()
    return log_line


def _strip_app_prefix(payload: str) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Strip app-style prefix and extract debug fields.
    
    Pattern: "<E> [#4] MMCap: ..." or "<D> [] GymeaThrift: ..."
    
    Returns:
        (stripped_payload, severity, tag, component)
    
    Never fails - always returns valid values.
    """
    # Ensure payload is a string
    if not isinstance(payload, str):
        if payload is None:
            return ("", None, None, None)
        try:
            payload = str(payload)
        except Exception:
            return ("", None, None, None)
    
    if not payload:
        return ("", None, None, None)
    
    severity = None
    tag = None
    component = None
    stripped = payload
    
    # Extract severity: <E>, <I>, <D>, <W>
    severity_match = re.search(r'<([IDEW])>', payload)
    if severity_match:
        severity = severity_match.group(1)
        # Remove severity marker
        stripped = (payload[:severity_match.start()] + " " + payload[severity_match.end():]).strip()
    
    # Extract tag: first bracket group after severity (may be empty or contain anything)
    # Pattern: [...] where content can be anything
    tag_match = re.search(r'\[(.*?)\]', stripped)
    if tag_match:
        tag_content = tag_match.group(1).strip()
        # Strip "#" prefix if present (e.g., "#4" -> "4")
        if tag_content.startswith('#'):
            tag_content = tag_content[1:].strip()
        tag = tag_content or None
        # Remove tag marker
        stripped = (stripped[:tag_match.start()] + " " + stripped[tag_match.end():]).strip()
    
    # Extract component: "ComponentName: message"
    # Look for pattern at start of stripped payload
    component_match = re.search(r'^([A-Z][a-zA-Z0-9_]+)\s*:\s*', stripped)
    if component_match:
        component = component_match.group(1)
        # Keep component in stripped payload (we'll use it in query_text)
        # stripped already starts with component, so no change needed
    
    return (stripped, severity, tag, component)


def _normalize_query_text(stripped_payload: str, component: Optional[str]) -> str:
    """
    Normalize payload for search query.
    
    Rules:
    1. Extract component and message portion
    2. Apply transport-prefix stripping to message portion
    3. Replace ports/integers/floats with placeholders
    4. Lowercase, collapse whitespace
    5. Include component in query_text if present
    
    Args:
        stripped_payload: Payload after app prefix stripping (e.g., "MMCap: localhost:9210:...")
        component: Component name if extracted (e.g., "MMCap")
    
    Returns:
        Normalized query text
    """
    if not stripped_payload:
        return ""
    
    # Split on first colon to separate component from message
    if ":" in stripped_payload:
        parts = stripped_payload.split(":", 1)
        comp_part = parts[0].strip()
        msg_part = parts[1].strip() if len(parts) > 1 else ""
        
        # Use extracted component if available, otherwise use comp_part
        comp_name = component or comp_part if comp_part else None
    else:
        comp_name = component
        msg_part = stripped_payload
    
    # Apply transport-prefix stripping to message portion
    # Pattern: "localhost:9210:Dyn-ultron:LIFTER ..." -> "LIFTER ..."
    # Look for pattern: word:port:word:ALLCAPS
    transport_pattern = r'^[a-z0-9._-]+:\d+:[a-z0-9._-]+:([A-Z][A-Z0-9_]+)\s+'
    match = re.match(transport_pattern, msg_part, re.IGNORECASE)
    if match:
        allcaps_token = match.group(1)
        rest = msg_part[match.end():].strip()
        msg_part = f"{allcaps_token} {rest}"
    
    # Replace ports with placeholder
    # Pattern: ":9210" -> ":<port>"
    msg_part = re.sub(r':\d{4,5}\b', ':<port>', msg_part)
    
    # Replace integers and floats with <num>
    # Be careful not to replace single digits in words
    msg_part = re.sub(r'\b\d+\.\d+\b', '<num>', msg_part)  # Floats first
    msg_part = re.sub(r'\b\d+\b', '<num>', msg_part)  # Then integers
    
    # Lowercase and normalize whitespace
    msg_normalized = msg_part.lower()
    msg_normalized = re.sub(r'\s+', ' ', msg_normalized).strip()
    
    # Build query text: include component if present
    if comp_name:
        comp_normalized = comp_name.lower()
        if msg_normalized:
            query_text = f"{comp_normalized} {msg_normalized}"
        else:
            query_text = comp_normalized
    else:
        query_text = msg_normalized
    
    return query_text


def _unknown_result(payload: str) -> Dict[str, Any]:
    """Return result dict for unknown route."""
    stripped_payload, severity, tag, component = _strip_app_prefix(payload)
    query_text = _normalize_query_text(stripped_payload, component)
    
    return {
        "route": "unknown",
        "confidence": 0.0,
        "payload": payload,
        "query_text": query_text,
        "severity": severity,
        "tag": tag,
        "component": component,
    }

