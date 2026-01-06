"""
Query candidate generation for multi-candidate search.

Generates deterministic query candidates from parsed log lines to improve
search reliability by trying multiple query formulations.

Example log output for MMCap query:
-----------------------------------
Search request: machine_id=..., query='2026-01-06T09:47:26.310054+11:00 RS20300529 Kareela0: <E> [#4] MMCap: localhost:9210:Dyn-ultron:LIFTER not at cap, instead at home.', debug=False, user=...
Log parsed: route=kareela, confidence=0.95, query_text='mmcap lifter not at cap, instead at home.'
Route filter will be applied: kareela
Generated 8 query candidates
Multi-candidate search: 8 candidates
Searching candidate 1/8: message_only = 'lifter not at cap, instead at home.'
Candidate 'message_only': 3 results (exact:0/partial:2/code:1)
Searching candidate 2/8: original_query_text = 'mmcap lifter not at cap, instead at home.'
Candidate 'original_query_text': 5 results (exact:1/partial:3/code:1)
...
Candidate search stats:
  message_only: 3 results (exact:0/partial:2/code:1)
  original_query_text: 5 results (exact:1/partial:3/code:1)
  bigram: 2 results (exact:0/partial:2/code:0)
  ...
Merge summary: 12 unique hits, 8 grouped results
Top 5 hits:
  1. error_key='MMCap: LIFTER not at cap' score=2.100, candidates=3, match_type=exact
  2. error_key='MMCap lifter error' score=1.800, candidates=2, match_type=partial
  ...
Search complete: machine_id=..., match_type=exact:2/partial:5/code:1, total_results=8, elapsed_ms=45ms
"""

import re
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# Common stop words to filter out for better search precision
_STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
    'to', 'was', 'will', 'with', 'get', 'got', 'go', 'goes', 'went',
    'this', 'these', 'they', 'them', 'their', 'there', 'then', 'than',
    'have', 'had', 'has', 'having', 'do', 'does', 'did', 'doing',
    'can', 'could', 'should', 'would', 'may', 'might', 'must'
}

# Extended stop words for strong token filtering
_STRONG_TOKEN_STOPWORDS = {
    'error', 'failed', 'attempt', 'responses', 'localhost', 'result', 
    'check', 'get', 'for', 'with', 'from', 'to', 'the', 'and', 'or', 
    'in', 'on', 'at', 'of'
}


def build_query_candidates(
    parsed: Dict[str, Any], 
    raw_query: str,
    enable_route_filter: bool = False
) -> List[Dict[str, Any]]:
    """
    Generate multiple deterministic query candidates from parsed log line.
    
    Args:
        parsed: Parsed log dict with route, query_text, component, payload, etc.
        raw_query: Original raw query string (for fallback)
        enable_route_filter: If True, set allowed_routes on candidates based on parsed route.
                           If False, never set allowed_routes (search all chunks).
    
    Returns:
        List of candidate dicts, each with:
        - name: string identifier (e.g., "component+message", "message_only")
        - text: string query text
        - weight: float (default 1.0)
        - allowed_routes: Optional[List[str]] (only set if enable_route_filter=True and route detected with confidence >= 0.8)
        - route_filter: Optional[str] (deprecated, for backward compatibility only)
    """
    candidates = []
    query_text = parsed.get('query_text', '').strip()
    component = parsed.get('component')
    payload = parsed.get('payload', '').strip()
    route = parsed.get('route', 'unknown')
    confidence = parsed.get('confidence', 0.0)
    
    # Determine allowed routes (only if filtering is enabled)
    allowed_routes = None
    route_filter = None  # For backward compatibility
    if enable_route_filter and route in ('kareela', 'gymea') and confidence >= 0.8:
        allowed_routes = [route, 'unknown']
        route_filter = route  # Keep for backward compatibility
    
    if not query_text and not payload:
        # Fallback to normalized raw query
        query_text = raw_query.lower().strip()
    
    if not query_text:
        return []
    
    # A) Extract message_only (component removed if present)
    message_only = None
    component_part = None
    
    if component:
        comp_lower = component.lower()
        # Check if query_text starts with component prefix
        if query_text.startswith(comp_lower + ' '):
            message_only = query_text[len(comp_lower) + 1:].strip()
            component_part = comp_lower
        elif ':' in payload:
            # Try to extract from payload: "Component: message"
            parts = payload.split(':', 1)
            if len(parts) == 2:
                payload_comp = parts[0].strip()
                payload_msg = parts[1].strip()
                # Normalize the message part
                message_only = _normalize_message(payload_msg)
                component_part = payload_comp.lower()
    else:
        # No component, use query_text as message_only
        message_only = query_text
    
    # If we still don't have message_only, extract from query_text by removing component
    if not message_only:
        # Try splitting on space if query_text might have component prefix
        parts = query_text.split(' ', 1)
        if len(parts) == 2 and len(parts[0]) > 2:
            # First part might be component
            message_only = parts[1]
            component_part = parts[0]
        else:
            message_only = query_text
    
    # A) message_only candidate
    if message_only and len(message_only.split()) >= 2:
        candidates.append({
            'name': 'message_only',
            'text': message_only,
            'weight': 1.0,
            'allowed_routes': allowed_routes,
            'route_filter': route_filter  # Backward compatibility
        })
    
    # B) component+message candidate (if component exists and not already in query_text)
    if component_part and message_only:
        comp_msg_text = f"{component_part} {message_only}".strip()
        # Only add if different from query_text
        if comp_msg_text != query_text and len(comp_msg_text.split()) >= 2:
            candidates.append({
                'name': 'component+message',
                'text': comp_msg_text,
                'weight': 1.0,
                'allowed_routes': allowed_routes,
                'route_filter': route_filter  # Backward compatibility
            })
    
    # Also add original query_text if not already included
    if query_text and not any(c['text'] == query_text for c in candidates):
        if len(query_text.split()) >= 2:
            candidates.append({
                'name': 'original_query_text',
                'text': query_text,
                'weight': 1.0,
                'allowed_routes': allowed_routes,
                'route_filter': route_filter  # Backward compatibility
            })
    
    # C) core_phrase candidates
    if message_only:
        tokens = message_only.split()
        if len(tokens) > 1:
            # Drop first token if it's ALLCAPS or looks like a part name
            first_token = tokens[0]
            if (first_token.isupper() and len(first_token) > 2) or _looks_like_part_name(first_token):
                core_phrase = ' '.join(tokens[1:])
                if len(core_phrase.split()) >= 2:
                    candidates.append({
                        'name': 'core_phrase',
                        'text': core_phrase,
                        'weight': 0.8,
                        'allowed_routes': allowed_routes,
                        'route_filter': route_filter  # Backward compatibility
                    })
            
            # Longest 4-8 token tail if message is long
            if len(tokens) > 8:
                for tail_len in [8, 6, 4]:
                    if len(tokens) >= tail_len:
                        tail_phrase = ' '.join(tokens[-tail_len:])
                        if len(tail_phrase.split()) >= 2:
                            candidates.append({
                                'name': f'core_phrase_tail_{tail_len}',
                                'text': tail_phrase,
                                'weight': 0.7,
                                'allowed_routes': allowed_routes,
                                'route_filter': route_filter  # Backward compatibility
                            })
                            break
    
    # D) bigrams/trigrams (limited)
    if message_only:
        tokens = [t for t in message_only.split() if t not in _STOP_WORDS and len(t) > 2]
        if len(tokens) >= 2:
            # Generate bigrams (up to 6 most informative)
            bigrams = []
            for i in range(len(tokens) - 1):
                bigram = f"{tokens[i]} {tokens[i+1]}"
                # Skip if both are stopwords (already filtered, but check length)
                if len(bigram.split()) == 2:
                    bigrams.append(bigram)
            
            # Take up to 6 unique bigrams
            seen_bigrams = set()
            for bigram in bigrams[:10]:  # Check more than needed
                if bigram not in seen_bigrams and len(seen_bigrams) < 6:
                    seen_bigrams.add(bigram)
                    candidates.append({
                        'name': 'bigram',
                        'text': bigram,
                        'weight': 0.6,
                        'allowed_routes': allowed_routes,
                        'route_filter': route_filter  # Backward compatibility
                    })
            
            # Generate a couple trigrams if message is long enough
            if len(tokens) >= 3:
                trigrams = []
                for i in range(min(len(tokens) - 2, 3)):  # Max 3 trigrams
                    trigram = f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}"
                    trigrams.append(trigram)
                
                for trigram in trigrams[:2]:  # Max 2 trigrams
                    candidates.append({
                        'name': 'trigram',
                        'text': trigram,
                        'weight': 0.7,
                        'allowed_routes': allowed_routes,
                        'route_filter': route_filter  # Backward compatibility
                    })

    # F) Strong token candidates (unigrams that look like code identifiers)
    MAX_STRONG_TOKENS = 8
    strong_tokens = _extract_strong_tokens(query_text, payload)
    
    for token in strong_tokens[:MAX_STRONG_TOKENS]:
        candidates.append({
            'name': 'strong_token',
            'text': token,
            'weight': 0.6,
            'allowed_routes': allowed_routes,
            'route_filter': route_filter  # Backward compatibility
        })

    # E) fallback_raw_payload (only if we have no good candidates)
    if not candidates and payload:
        normalized_payload = _normalize_message(payload)
        if normalized_payload and len(normalized_payload.split()) >= 2:
            candidates.append({
                'name': 'fallback_raw_payload',
                'text': normalized_payload,
                'weight': 0.5,
                'allowed_routes': allowed_routes,
                'route_filter': route_filter  # Backward compatibility
            })
    
    # Deduplicate by exact text
    seen_texts = set()
    unique_candidates = []
    for cand in candidates:
        if cand['text'] not in seen_texts:
            seen_texts.add(cand['text'])
            # Filter out candidates with <2 tokens unless it's the only option
            token_count = len(cand['text'].split())
            if token_count >= 2 or len(unique_candidates) == 0:
                unique_candidates.append(cand)
    
    return unique_candidates if unique_candidates else candidates


def _normalize_message(message: str) -> str:
    """Normalize a message string (lowercase, collapse whitespace)."""
    if not message:
        return ""
    normalized = message.lower()
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _looks_like_part_name(token: str) -> bool:
    """Check if token looks like a part/device name (ALLCAPS, mixed case with numbers)."""
    if not token:
        return False
    # ALLCAPS with length > 2
    if token.isupper() and len(token) > 2:
        return True
    # Mixed case with numbers/underscores (e.g., "LIFTER", "Dyn-ultron")
    if re.match(r'^[A-Z][A-Z0-9_-]+$', token):
        return True
    return False


def _extract_strong_tokens(query_text: str, payload: str) -> List[str]:
    """
    Extract strong tokens from query_text and payload that look like code identifiers.
    
    Rules:
    - Token length >= 4 OR contains '_' OR contains digits
    - Exclude stopwords
    - Keep tokens that look like code identifiers (CamelCase, ALLCAPS, underscores)
    
    Returns sorted list (prefer tokens with underscores/ALLCAPS/digits first).
    """
    if not query_text and not payload:
        return []
    
    # Combine text sources
    combined_text = f"{query_text} {payload}".strip()
    if not combined_text:
        return []
    
    # Extract tokens: split on non-alphanumeric/underscore, preserve case initially
    tokens_raw = re.findall(r'[A-Za-z0-9_]+', combined_text)
    
    strong_tokens = []
    seen = set()
    
    for token in tokens_raw:
        token_lower = token.lower()
        
        # Skip if already seen (case-insensitive)
        if token_lower in seen:
            continue
        
        # Rule: length >= 4 OR contains '_' OR contains digits
        has_underscore = '_' in token
        has_digits = bool(re.search(r'\d', token))
        is_long_enough = len(token) >= 4
        
        if not (is_long_enough or has_underscore or has_digits):
            continue
        
        # Exclude stopwords
        if token_lower in _STRONG_TOKEN_STOPWORDS:
            continue
        
        # Check if looks like code identifier
        looks_like_code = (
            has_underscore or
            token.isupper() or
            (token[0].isupper() and any(c.islower() for c in token[1:])) or  # CamelCase
            has_digits
        )
        
        if looks_like_code or is_long_enough:
            seen.add(token_lower)
            # Score for sorting: prefer underscores, ALLCAPS, digits
            score = 0
            if has_underscore:
                score += 3
            if token.isupper():
                score += 2
            if has_digits:
                score += 1
            if len(token) >= 8:
                score += 1
            
            strong_tokens.append((score, token_lower))
    
    # Sort by score descending, then alphabetically
    strong_tokens.sort(key=lambda x: (-x[0], x[1]))
    
    return [token for _, token in strong_tokens]

