"""
Chunk index search logic.

Searches pre-indexed codebase chunks for error messages.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Union, Set

logger = logging.getLogger(__name__)

# Stop words for token overlap search (expanded with domain generic terms)
_TOKEN_STOPWORDS = {
    'error', 'failed', 'attempt', 'responses', 'check', 'instead', 'home',
    'localhost', 'endpoint', 'properties', 'supported', 'result', 'driver',
    'state', 'starting', 'finished', 'completed', 'changing', 'response',
    'request', 'get', 'set', 'reset', 'from', 'with', 'that', 'this',
    'then', 'than', 'into', 'over', 'under', 'not', 'for', 'to', 'the',
    'and', 'or', 'in', 'on', 'at', 'of', 'a', 'an', 'are', 'as', 'be',
    'by', 'has', 'he', 'is', 'it', 'its', 'was', 'will', 'these', 'they',
    'them', 'their', 'there'
}


def _extract_strong_tokens(text: str) -> Set[str]:
    """
    Extract strong tokens (identifier-like) from text.
    
    Strong tokens are:
    - Contains '_' OR digits OR length>=5 (not in stopwords) OR has camelcase in raw payload
    
    Examples: result_dev_err, gymeamux, getvcs, mmcap, lifter, vc, cyan
    
    Returns set of strong token strings (lowercased).
    """
    if not text:
        return set()
    
    # Preserve case initially to detect CamelCase
    tokens_raw = re.findall(r'[A-Za-z0-9_]+', text)
    
    strong_tokens = set()
    seen = set()
    
    for token in tokens_raw:
        token_lower = token.lower()
        
        if token_lower in seen or token_lower in _TOKEN_STOPWORDS:
            continue
        
        # Check if strong token criteria
        has_underscore = '_' in token
        has_digits = bool(re.search(r'\d', token))
        is_long_enough = len(token) >= 5
        has_camelcase = len(token) > 1 and token[0].isupper() and any(c.islower() for c in token[1:])
        
        if has_underscore or has_digits or (is_long_enough and token_lower not in _TOKEN_STOPWORDS) or has_camelcase:
            strong_tokens.add(token_lower)
            seen.add(token_lower)
    
    return strong_tokens


def _tokenize_for_overlap(text: str) -> Set[str]:
    """
    Tokenize text for token overlap search.
    
    Rules:
    - Lowercase
    - Split on non-alphanumeric/underscore
    - Keep tokens: len>=4 OR contains '_' OR contains digits
    - Remove stopwords
    
    Returns set of token strings.
    """
    if not text:
        return set()
    
    # Split on non-alphanumeric/underscore
    tokens = re.findall(r'[A-Za-z0-9_]+', text.lower())
    
    result = set()
    for token in tokens:
        # Keep if: len>=4 OR contains '_' OR contains digits
        has_underscore = '_' in token
        has_digits = bool(re.search(r'\d', token))
        is_long_enough = len(token) >= 4
        
        if (is_long_enough or has_underscore or has_digits) and token not in _TOKEN_STOPWORDS:
            result.add(token)
    
    return result


def _token_overlap_search(
    candidate_text: str,
    chunks_dict: Dict[str, Any],
    seen_chunk_ids: Set[str],
    seen_error_keys: Set[str],
    candidate_strong_tokens: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Token overlap search: find chunks where token sets overlap.
    
    Args:
        candidate_text: Query text to search for
        chunks_dict: Dict of chunk_id -> chunk
        seen_chunk_ids: Set of chunk IDs already included (to avoid duplicates)
        seen_error_keys: Set of error keys already included
        candidate_strong_tokens: Optional set of strong tokens from candidate (for gating)
    
    Returns:
        List of result dicts with match_type='token_overlap'
    """
    # Tokenize candidate text
    candidate_tokens = _tokenize_for_overlap(candidate_text)
    
    if not candidate_tokens:
        return []
    
    # Extract strong tokens from candidate if not provided
    if candidate_strong_tokens is None:
        candidate_strong_tokens = _extract_strong_tokens(candidate_text)
    
    results = []
    
    for chunk_id, chunk in chunks_dict.items():
        # Skip if already included
        if chunk_id in seen_chunk_ids:
            continue
        
        # Build searchable text from chunk fields
        signature = chunk.get('signature', '') or ''
        leading_comment = chunk.get('leading_comment', '') or ''
        docstring = chunk.get('docstring', '') or ''
        code = chunk.get('code', '') or ''
        
        # Also check error_key from error_messages if available
        error_key_parts = []
        for err_msg in chunk.get('error_messages', []):
            error_key_parts.append(err_msg.get('message', ''))
        
        searchable_text = ' '.join([
            signature,
            leading_comment,
            docstring,
            code,
            ' '.join(error_key_parts)
        ])
        
        # Tokenize chunk text
        chunk_tokens = _tokenize_for_overlap(searchable_text)
        
        # Extract strong tokens from chunk
        chunk_strong_tokens = _extract_strong_tokens(searchable_text)
        
        # Calculate overlap
        overlap = candidate_tokens & chunk_tokens
        
        # Calculate strong token overlap
        overlap_strong = candidate_strong_tokens & chunk_strong_tokens
        
        # Gating: require strong token overlap
        # Accept chunk only if:
        # (len(overlap_strong) >= 1 AND len(overlap) >= 2) OR (len(overlap_strong) >= 2)
        if not ((len(overlap_strong) >= 1 and len(overlap) >= 2) or (len(overlap_strong) >= 2)):
            continue
        
        # Calculate score: prioritize strong tokens
        # score = min(0.6, 0.12 * len(overlap_strong) + 0.03 * (len(overlap) - len(overlap_strong)))
        base_score = min(0.6, 0.12 * len(overlap_strong) + 0.03 * max(0, len(overlap) - len(overlap_strong)))
        
        # Build matched_text showing overlapping tokens (prioritize strong tokens)
        overlap_list = sorted(list(overlap))
        overlap_strong_list = sorted(list(overlap_strong))
        if len(overlap_strong_list) > 0:
            if len(overlap_strong_list) <= 5:
                matched_text = f"overlap: {', '.join(overlap_strong_list)} (strong: {len(overlap_strong)}, total: {len(overlap)})"
            else:
                matched_text = f"overlap: {', '.join(overlap_strong_list[:5])}, ... (strong: {len(overlap_strong)}, total: {len(overlap)})"
        else:
            if len(overlap_list) <= 5:
                matched_text = f"overlap: {', '.join(overlap_list)}"
            else:
                matched_text = f"overlap: {', '.join(overlap_list[:5])}, ... ({len(overlap_list)} tokens)"
        
        # Create error key from function/file info
        file_path = chunk.get('file_path', 'unknown')
        function_name = chunk.get('function_name', 'unknown')
        error_key = f"Token overlap: {function_name} in {file_path}"
        
        # Avoid duplicate error keys
        if error_key in seen_error_keys:
            continue
        
        seen_error_keys.add(error_key)
        seen_chunk_ids.add(chunk_id)
        
        results.append({
            'error_key': error_key,
            'chunks': [chunk],
            'match_type': 'token_overlap',
            'score': base_score,
            'matched_text': matched_text,
            'overlap_strong_count': len(overlap_strong),
            'overlap_strong_tokens': list(overlap_strong_list[:5])  # Store sample for logging
        })
    
    return results


def normalize_error_message(message: str) -> str:
    """
    Normalize error message for searching.
    
    Must match the normalization used in ingest.py when building the index:
    - Lowercase
    - Strip whitespace
    
    Note: ingest.py uses error_msg.lower().strip() (no whitespace collapsing)
    """
    if not message:
        return ""
    normalized = message.lower().strip()
    # Do NOT collapse whitespace - must match ingest.py normalization exactly
    return normalized


def _token_overlap_score(query_tokens: List[str], key_tokens: List[str]) -> float:
    """Calculate token overlap score between query and key."""
    if not query_tokens or not key_tokens:
        return 0.0
    
    query_set = set(query_tokens)
    key_set = set(key_tokens)
    
    intersection = query_set & key_set
    union = query_set | key_set
    
    if not union:
        return 0.0
    
    # Jaccard similarity
    return len(intersection) / len(union)


def _length_proximity_score(query_len: int, key_len: int) -> float:
    """Calculate length proximity score (closer lengths = higher score)."""
    if query_len == 0 or key_len == 0:
        return 0.0
    
    diff = abs(query_len - key_len)
    max_len = max(query_len, key_len)
    
    # Score decreases as length difference increases
    return 1.0 - (diff / max_len)


# Common stop words to filter out for better search precision
_STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
    'to', 'was', 'will', 'with', 'get', 'got', 'go', 'goes', 'went',
    'this', 'these', 'they', 'them', 'their', 'there', 'then', 'than',
    'have', 'had', 'has', 'having', 'do', 'does', 'did', 'doing',
    'can', 'could', 'should', 'would', 'may', 'might', 'must'
}


def _filter_significant_tokens(tokens: List[str]) -> List[str]:
    """Filter out stop words and very short tokens."""
    return [t for t in tokens if len(t) > 2 and t not in _STOP_WORDS]


def _extract_match_excerpt(query: str, text: str, context_chars: int = 100) -> str:
    """
    Extract a relevant excerpt from text that shows why it matched the query.
    Returns a snippet around the match location.
    """
    query_lower = query.lower()
    text_lower = text.lower()
    
    # Find the position of the query in the text
    pos = text_lower.find(query_lower)
    if pos >= 0:
        # Extract context around the match
        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(query) + context_chars)
        excerpt = text[start:end]
        # Add ellipsis if needed
        if start > 0:
            excerpt = '...' + excerpt
        if end < len(text):
            excerpt = excerpt + '...'
        return excerpt.strip()
    
    # If exact phrase not found, try to find significant tokens
    query_tokens = _filter_significant_tokens(query_lower.split())
    if not query_tokens:
        return ""
    
    # Find first significant token
    first_token = query_tokens[0] if query_tokens else None
    if first_token and first_token in text_lower:
        pos = text_lower.find(first_token)
        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(first_token) + context_chars)
        excerpt = text[start:end]
        if start > 0:
            excerpt = '...' + excerpt
        if end < len(text):
            excerpt = excerpt + '...'
        return excerpt.strip()
    
    return ""


def _calculate_phrase_match_score(query: str, text: str) -> float:
    """
    Calculate score for phrase match in text.
    Higher score for:
    - Exact phrase match
    - Most tokens in order
    - Significant tokens (not stop words)
    """
    query_lower = query.lower()
    text_lower = text.lower()
    
    # Exact phrase match gets highest score
    if query_lower in text_lower:
        return 1.0
    
    # Tokenize and filter
    query_tokens = _filter_significant_tokens(query_lower.split())
    if not query_tokens:
        return 0.0
    
    text_tokens = text_lower.split()
    
    # Check how many significant tokens match
    matched_tokens = sum(1 for token in query_tokens if token in text_lower)
    token_ratio = matched_tokens / len(query_tokens)
    
    # Require at least 50% of significant tokens to match
    if token_ratio < 0.5:
        return 0.0
    
    # Check for token order (bigrams/trigrams)
    order_score = 0.0
    if len(query_tokens) >= 2:
        # Check if consecutive tokens appear in order
        ordered_pairs = 0
        for i in range(len(query_tokens) - 1):
            token1 = query_tokens[i]
            token2 = query_tokens[i + 1]
            # Find positions of tokens in text
            if token1 in text_lower and token2 in text_lower:
                pos1 = text_lower.find(token1)
                pos2 = text_lower.find(token2, pos1)
                if pos2 > pos1:  # Token2 appears after token1
                    ordered_pairs += 1
        if len(query_tokens) > 1:
            order_score = ordered_pairs / (len(query_tokens) - 1)
    
    # Combined score: token ratio + order preservation
    score = (token_ratio * 0.6) + (order_score * 0.4)
    
    return score


def _extract_search_phrases(error_message: str) -> List[str]:
    """
    Extract search phrases from an error message.
    
    For messages with dynamic parts, extract the static parts that are likely in the code.
    Returns a list of phrases ordered by specificity (most specific first).
    
    Strategy: Only extract meaningful, specific phrases to avoid too many false positives.
    """
    normalized = normalize_error_message(error_message)
    phrases = []
    
    import re
    
    # Remove parts that look like dynamic content (host:port:device patterns)
    colon_pattern = r'[a-zA-Z0-9._-]+:[0-9]+:[a-zA-Z0-9._-]+(:[a-zA-Z0-9._-]+)*'
    cleaned = re.sub(colon_pattern, '', normalized)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    words = cleaned.split()
    
    # Strategy: Extract meaningful phrases, but be more lenient
    # 1. Full cleaned message (most specific)
    if cleaned and len(cleaned) >= 8:  # Less restrictive: 8 chars instead of 10
        phrases.append(cleaned)
    
    # 2. Extract phrases of 3+ words (less restrictive than 4+)
    if len(words) >= 3:
        # Try the full phrase first
        full_phrase = ' '.join(words)
        if full_phrase not in phrases:
            phrases.append(full_phrase)
        
        # Try last 3-5 words (often the key part)
        for length in [min(5, len(words)), 4, 3]:
            if len(words) >= length:
                phrase = ' '.join(words[-length:])
                if phrase and phrase not in phrases and len(phrase) >= 8:  # Less restrictive: 8 chars
                    phrases.append(phrase)
    
    # 3. Only add capitalized words if they're part of a longer phrase context
    # Don't search for single words like "LIFTER" alone - too many false positives
    # Instead, look for capitalized words + following words
    capitalized_words = re.findall(r'\b([A-Z][a-zA-Z0-9]+)\s+([a-z]+(?:\s+[a-z]+)*)', error_message)
    for cap_word, following in capitalized_words:
        phrase = f"{cap_word.lower()} {following.lower()}"
        if len(phrase) >= 10 and phrase not in phrases:
            phrases.append(phrase)
    
    # 4. If we have very few phrases, add the original normalized message
    if len(phrases) < 2 and normalized and len(normalized) >= 8:  # Less restrictive
        if normalized not in phrases:
            phrases.insert(0, normalized)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_phrases = []
    for phrase in phrases:
        phrase_lower = phrase.lower().strip()
        # Keep phrases that are meaningful (at least 8 chars, 1+ words) - less restrictive
        if phrase_lower not in seen and len(phrase_lower) >= 8 and len(phrase_lower.split()) >= 1:
            seen.add(phrase_lower)
            unique_phrases.append(phrase_lower)
    
    # If we still have nothing, return the normalized message
    return unique_phrases if unique_phrases else [normalized] if normalized else []


def search_chunk_index(
    error_message: str, 
    index_data: Dict[str, Any],
    allowed_routes: Optional[Union[str, Set[str], List[str]]] = None,
    enable_route_filter: bool = False
) -> List[Dict[str, Any]]:
    """
    Search chunk-based index for error message.
    
    Strategy:
    1. Exact match: lookup in error_index[normalized_message]
    2. Substring match in error_index keys: find keys that contain the normalized query as substring
    3. Code content search: search actual code, docstrings, comments for exact substring match
       (NOT word-based - searches for the exact string in codebase)
    
    The code content search is important because indexed error messages may not be accurate,
    but searching the actual code will find matches.
    
    Args:
        error_message: Error message to search for
        index_data: Full index JSON structure with 'chunks' and 'error_index'
        allowed_routes: Optional route(s) to filter by. Can be:
            - None: no filtering
            - str: single route (backward compatibility, converted to set)
            - Set[str] or List[str]: multiple allowed routes (e.g., {"kareela", "unknown"})
    
    Returns:
        List of grouped results, each with error_key and chunks
    """
    if not error_message or not index_data:
        return []
    
    # Extract multiple search phrases (handles dynamic parts in error messages)
    search_phrases = _extract_search_phrases(error_message)
    if not search_phrases:
        return []
    
    # Primary query is the first (most specific) phrase
    normalized_query = search_phrases[0]
    original_query = error_message.strip()
    
    error_index = index_data.get('error_index', {})
    chunks_dict = {chunk['chunk_id']: chunk for chunk in index_data.get('chunks', [])}
    
    # Normalize allowed_routes to a set (support backward compatibility with string)
    allowed_routes_set = None
    if allowed_routes:
        if isinstance(allowed_routes, str):
            allowed_routes_set = {allowed_routes}
        elif isinstance(allowed_routes, (set, list)):
            allowed_routes_set = set(allowed_routes)
        else:
            logger.warning(f"Invalid allowed_routes type: {type(allowed_routes)}, ignoring filter")
    
    # Apply route filter if provided AND filtering is enabled
    if enable_route_filter and allowed_routes_set:
        original_count = len(chunks_dict)
        chunks_dict = {
            cid: chunk for cid, chunk in chunks_dict.items()
            if chunk.get('route') in allowed_routes_set
        }
        routes_list = sorted(list(allowed_routes_set))
        logger.info(
            f"Route filter applied: routes={routes_list}, "
            f"{len(chunks_dict)}/{original_count} chunks remain"
        )
    elif not enable_route_filter and allowed_routes_set:
        # Filtering disabled but allowed_routes was provided (from candidates or default)
        # Log once that filtering is disabled
        routes_list = sorted(list(allowed_routes_set))
        logger.debug(
            f"Route filtering disabled: would have filtered routes={routes_list} (not applied) - "
            f"searching all {len(chunks_dict)} chunks"
        )
    
    results = []
    seen_error_keys = set()
    seen_chunk_ids = set()  # Track chunks we've already added to avoid duplicates
    
    # Strategy 1: Exact match in error_index (try all phrases)
    for phrase in search_phrases:
        if phrase in error_index:
            for match_info in error_index[phrase]:
                chunk_id = match_info.get('chunk_id')
                if chunk_id and chunk_id in chunks_dict:
                    error_key = match_info.get('original_message', normalized_query)
                    if error_key not in seen_error_keys:
                        seen_error_keys.add(error_key)
                        seen_chunk_ids.add(chunk_id)
                        chunk = chunks_dict[chunk_id]
                        matched_text = error_key
                        results.append({
                            'error_key': error_key,
                            'chunks': [chunk],
                            'match_type': 'exact',
                            'score': 1.0 * 4.0,  # Boost exact matches
                            'matched_text': matched_text
                        })
    
    # Strategy 2: Substring match in error_index keys
    # Try all phrases, but score by specificity (longer phrases = higher score)
    if not results:
        for phrase in search_phrases:  # Try all phrases
            for error_key_normalized, match_list in error_index.items():
                if error_key_normalized in seen_error_keys:
                    continue
                
                # Check if phrase is contained as a substring in error_key
                if phrase in error_key_normalized:
                    seen_error_keys.add(error_key_normalized)
                    
                    # Get all chunks for this error key
                    chunks = []
                    for match_info in match_list:
                        chunk_id = match_info.get('chunk_id')
                        if chunk_id and chunk_id in chunks_dict:
                            if chunk_id not in seen_chunk_ids:
                                chunks.append(chunks_dict[chunk_id])
                                seen_chunk_ids.add(chunk_id)
                    
                    if chunks:
                        original_msg = match_list[0].get('original_message', error_key_normalized) if match_list else error_key_normalized
                        # Score based on phrase length (longer = more specific = higher score)
                        # Range: 0.5 (short) to 0.8 (long)
                        phrase_score = min(0.8, 0.5 + (len(phrase) / 100.0))
                        results.append({
                            'error_key': original_msg,
                            'chunks': chunks,
                            'match_type': 'partial',
                            'score': phrase_score * 4.0,  # Boost partial matches
                            'matched_text': original_msg
                        })
    
    # Strategy 3: Code content search - search actual code for exact string match
    # This is important because indexed error messages may not be accurate
    # Search in: code, docstring, leading_comment, signature
    # Use all phrases, but score by specificity
    code_search_phrases = search_phrases  # Try all phrases
    
    for chunk in index_data.get('chunks', []):
        chunk_id = chunk.get('chunk_id')
        if chunk_id in seen_chunk_ids:
            continue  # Already added from error_index match
        
        # Search in code content (case-insensitive for normalized query)
        code = chunk.get('code', '')
        docstring = chunk.get('docstring', '') or ''
        leading_comment = chunk.get('leading_comment', '') or ''
        signature = chunk.get('signature', '') or ''
        
        # Combine all text fields for searching
        searchable_text = ' '.join([code, docstring, leading_comment, signature])
        searchable_text_lower = searchable_text.lower()
        
        # Try each search phrase to find matches (only most specific ones)
        matched_phrase = None
        best_match_length = 0
        for phrase in code_search_phrases:
            if phrase in searchable_text_lower:
                # Prefer longer, more specific matches
                if len(phrase) > best_match_length:
                    matched_phrase = phrase
                    best_match_length = len(phrase)
        
        # Only add if we found a meaningful match (at least 8 chars)
        if matched_phrase and len(matched_phrase) >= 8:
            # Find the actual matched text (preserve original case)
            matched_text = ""
            # Try to find the match in original text
            pos = searchable_text_lower.find(matched_phrase)
            if pos >= 0:
                # Extract context around match (preserve original case)
                start = max(0, pos - 80)
                end = min(len(searchable_text), pos + len(matched_phrase) + 80)
                matched_text = searchable_text[start:end]
                if start > 0:
                    matched_text = '...' + matched_text
                if end < len(searchable_text):
                    matched_text = matched_text + '...'
                matched_text = matched_text.strip()
            
            if not matched_text:
                # Fallback: use function name and file path
                matched_text = f"{chunk.get('function_name', 'unknown')} in {chunk.get('file_path', 'unknown')}"
            
            # Create error key from function/file info
            file_path = chunk.get('file_path', 'unknown')
            function_name = chunk.get('function_name', 'unknown')
            error_key = f"Code match: {function_name} in {file_path}"
            
            if error_key not in seen_error_keys:
                seen_error_keys.add(error_key)
                seen_chunk_ids.add(chunk_id)
                results.append({
                    'error_key': error_key,
                    'chunks': [chunk],
                    'match_type': 'code_search',
                    'score': 0.6 * 1.5,  # Boost code matches
                    'matched_text': matched_text
                })
    
    # Sort results: exact matches first, then partial, then code_search, all by score
    results.sort(key=lambda x: (
        x['match_type'] != 'exact',  # exact first
        x['match_type'] == 'code_search',  # code_search last
        -x['score']  # then by score descending
    ))
    
    # Strategy 4: Token overlap search (for strong tokens and when results are sparse)
    # Run if results are small OR if the query is a single token (likely a strong_token candidate)
    should_run_token_overlap = (
        len(results) < 5 or
        len(search_phrases[0].split()) == 1  # Single token query
    )
    
    if should_run_token_overlap:
        # Extract strong tokens from query for gating
        candidate_strong_tokens = _extract_strong_tokens(normalized_query)
        
        token_overlap_results = _token_overlap_search(
            normalized_query,
            chunks_dict,
            seen_chunk_ids,
            seen_error_keys,
            candidate_strong_tokens=candidate_strong_tokens
        )
        results.extend(token_overlap_results)
    
    # Re-sort results after adding token_overlap
    results.sort(key=lambda x: (
        x['match_type'] != 'exact',  # exact first
        x['match_type'] == 'code_search',  # code_search last
        x['match_type'] == 'token_overlap',  # token_overlap after code_search
        -x['score']  # then by score descending
    ))
    
    # Apply limits: cap token_overlap results to 10 unless no exact/partial results
    exact_partial_count = sum(1 for r in results if r.get('match_type') in ('exact', 'partial'))
    token_overlap_results = [r for r in results if r.get('match_type') == 'token_overlap']
    other_results = [r for r in results if r.get('match_type') != 'token_overlap']
    
    MAX_GROUPED_RESULTS = 25
    MAX_TOKEN_OVERLAP_RESULTS = 10
    if exact_partial_count == 0:
        # If no exact/partial, allow more token_overlap
        limited_token_overlap = token_overlap_results[:MAX_GROUPED_RESULTS]
    else:
        # Otherwise cap token_overlap to 10
        limited_token_overlap = token_overlap_results[:MAX_TOKEN_OVERLAP_RESULTS]
    
    # Recombine and limit total
    final_results = other_results + limited_token_overlap
    final_results.sort(key=lambda x: (
        x.get('match_type') != 'exact',
        x.get('match_type') == 'code_search',
        x.get('match_type') == 'token_overlap',
        -x.get('score', 0)
    ))
    
    return final_results[:MAX_GROUPED_RESULTS]


def search_chunk_index_multi(
    query_candidates: List[Dict[str, Any]],
    index_data: Dict[str, Any],
    allowed_routes: Optional[Union[str, Set[str], List[str]]] = None,
    enable_route_filter: bool = False
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Search using multiple query candidates and merge results.
    
    Args:
        query_candidates: List of candidate dicts with 'name', 'text', 'weight', 'allowed_routes'
        index_data: Full index JSON structure
        allowed_routes: Optional default allowed routes (can be overridden per candidate).
            Can be str, Set[str], or List[str] for backward compatibility.
    
    Returns:
        Tuple of (merged_results, debug_info)
        - merged_results: List of grouped results (same format as search_chunk_index)
        - debug_info: Dict with candidate stats and merge summary
    """
    if not query_candidates or not index_data:
        return ([], {})
    
    # Track results by (error_key, chunk_id) pair
    merged_hits = {}  # (error_key, chunk_id) -> {result dict, scores, candidates}
    candidate_stats = []
    
    logger.info(f"Multi-candidate search: {len(query_candidates)} candidates")
    
    # Log route filtering status once
    if not enable_route_filter:
        logger.debug("Route filtering disabled: searching all chunks (candidate-level allowed_routes ignored)")
    
    # Search each candidate
    for i, candidate in enumerate(query_candidates):
        candidate_name = candidate.get('name', f'candidate_{i}')
        candidate_text = candidate.get('text', '')
        candidate_weight = candidate.get('weight', 1.0)
        # Support both 'route_filter' (old) and 'allowed_routes' (new) for backward compatibility
        candidate_allowed_routes = candidate.get('allowed_routes') or candidate.get('route_filter') or allowed_routes
        
        if not candidate_text:
            continue
        
        logger.debug(f"Searching candidate {i+1}/{len(query_candidates)}: {candidate_name} = '{candidate_text[:60]}...'")
        
        try:
            # Search with this candidate
            results = search_chunk_index(
                candidate_text, 
                index_data, 
                allowed_routes=candidate_allowed_routes,
                enable_route_filter=enable_route_filter
            )
            
            # Compute match_counts from results (always compute safely)
            match_counts = {'exact': 0, 'partial': 0, 'code_search': 0, 'token_overlap': 0}
            if results:
                for r in results:
                    match_type = r.get('match_type', 'partial')
                    if match_type in match_counts:
                        match_counts[match_type] += 1
            
            # Normalize allowed_routes for logging
            routes_str = None
            if candidate_allowed_routes:
                if isinstance(candidate_allowed_routes, str):
                    routes_str = [candidate_allowed_routes]
                elif isinstance(candidate_allowed_routes, (set, list)):
                    routes_str = sorted(list(set(candidate_allowed_routes)))
            
            # Package candidate stat (safe - match_counts always defined)
            candidate_stat = {
                'name': candidate_name,
                'text': candidate_text,
                'weight': candidate_weight,
                'allowed_routes': routes_str,
                'total_results': len(results) if results else 0,
                'match_counts': match_counts.copy()  # Copy to avoid mutation
            }
            candidate_stats.append(candidate_stat)
            
            # Extract and log strong tokens for this candidate
            candidate_strong_tokens = _extract_strong_tokens(candidate_text)
            strong_tokens_display = sorted(list(candidate_strong_tokens))[:12]
            strong_tokens_str = ', '.join(strong_tokens_display)
            if len(candidate_strong_tokens) > 12:
                strong_tokens_str += f' ... ({len(candidate_strong_tokens)} total)'
            
            # Log candidate (safe - match_counts always defined)
            logger.debug(
                f"Candidate '{candidate_name}'(\"{candidate_text[:60]}...\"): {len(results) if results else 0} results "
                f"(exact:{match_counts['exact']}/partial:{match_counts['partial']}/"
                f"code:{match_counts['code_search']}/token_overlap:{match_counts['token_overlap']}) "
                f"strong_tokens=[{strong_tokens_str}]"
            )
            
            # Merge results into merged_hits
            for result in results:
                error_key = result.get('error_key', 'unknown')
                chunks = result.get('chunks', [])
                match_type = result.get('match_type', 'partial')
                base_score = result.get('score', 0.0)
                matched_text = result.get('matched_text', '')
                
                # Weighted score for this candidate
                weighted_score = base_score * candidate_weight
                
                for chunk in chunks:
                    chunk_id = chunk.get('chunk_id', '')
                    if not chunk_id:
                        continue
                    
                    key = (error_key, chunk_id)
                    
                    if key not in merged_hits:
                        # First time seeing this hit
                        merged_hits[key] = {
                            'error_key': error_key,
                            'chunk': chunk,
                            'match_type': match_type,  # Use best match_type (exact > partial > code_search)
                            'matched_text': matched_text,
                            'scores': [],
                            'candidates_hit': [],
                            'aggregate_score': 0.0
                        }
                    
                    # Add to this hit's scores and candidates
                    merged_hits[key]['scores'].append(weighted_score)
                    merged_hits[key]['candidates_hit'].append(candidate_name)
                    
                    # Update match_type to best (exact > partial > code_search > token_overlap)
                    current_type = merged_hits[key]['match_type']
                    type_priority = {'exact': 4, 'partial': 3, 'code_search': 2, 'token_overlap': 1}
                    if type_priority.get(match_type, 0) > type_priority.get(current_type, 0):
                        merged_hits[key]['match_type'] = match_type
                        merged_hits[key]['matched_text'] = matched_text
        
        except Exception as e:
            logger.error(f"Error searching candidate '{candidate_name}': {e}", exc_info=True)
            # On error, still create stat entry but mark as error
            # This ensures we don't lose track of which candidates failed
            candidate_stats.append({
                'name': candidate_name,
                'text': candidate_text,
                'weight': candidate_weight,
                'total_results': 0,
                'match_counts': {'exact': 0, 'partial': 0, 'code_search': 0, 'token_overlap': 0},
                'error': str(e)
            })
            continue  # Skip to next candidate
    
    # Calculate aggregate scores with multi-candidate bonus
    for key, hit in merged_hits.items():
        scores = hit['scores']
        candidate_count = len(hit['candidates_hit'])
        
        # Base score: sum of weighted scores
        base_agg_score = sum(scores)
        
        # Multi-candidate bonus: +0.1 per additional candidate (max +0.3)
        bonus = min(0.3, (candidate_count - 1) * 0.1)
        
        hit['aggregate_score'] = base_agg_score + bonus
    
    # Convert merged_hits to grouped results format
    # Group by error_key (since that's how the API expects results)
    grouped_results = {}  # error_key -> list of chunks with scores
    
    for (error_key, chunk_id), hit in merged_hits.items():
        if error_key not in grouped_results:
            grouped_results[error_key] = {
                'error_key': error_key,
                'chunks': [],
                'match_type': hit['match_type'],
                'score': hit['aggregate_score'],
                'matched_text': hit['matched_text']
            }
        
        # Limit chunks per group
        MAX_CHUNKS_PER_GROUP = 3
        if len(grouped_results[error_key]['chunks']) < MAX_CHUNKS_PER_GROUP:
            grouped_results[error_key]['chunks'].append(hit['chunk'])
    
    # Convert to list and sort by aggregate score (descending)
    merged_results = list(grouped_results.values())
    merged_results.sort(key=lambda x: -x['score'])
    
    # Apply limits: cap token_overlap results to 10 unless no exact/partial results
    exact_partial_count = sum(1 for r in merged_results if r.get('match_type') in ('exact', 'partial'))
    token_overlap_results = [r for r in merged_results if r.get('match_type') == 'token_overlap']
    other_results = [r for r in merged_results if r.get('match_type') != 'token_overlap']
    
    MAX_GROUPED_RESULTS = 25
    MAX_TOKEN_OVERLAP_RESULTS = 10
    if exact_partial_count == 0:
        # If no exact/partial, allow more token_overlap
        limited_token_overlap = token_overlap_results[:MAX_GROUPED_RESULTS]
    else:
        # Otherwise cap token_overlap to 10
        limited_token_overlap = token_overlap_results[:MAX_TOKEN_OVERLAP_RESULTS]
    
    # Recombine and limit total
    final_results = other_results + limited_token_overlap
    final_results.sort(key=lambda x: (
        x.get('match_type') != 'exact',
        x.get('match_type') == 'code_search',
        x.get('match_type') == 'token_overlap',
        -x.get('score', 0)
    ))
    
    merged_results = final_results[:MAX_GROUPED_RESULTS]
    
    # Build debug info
    debug_info = {
        'candidates': candidate_stats,
        'total_unique_hits': len(merged_hits),
        'total_grouped_results': len(merged_results),
        'top_hits': []
    }
    
    # Add top hits with candidate info from merged_hits
    for result in merged_results[:5]:
        error_key = result['error_key']
        # Find matching hit to get candidate info
        hit_info = None
        for (ek, cid), hit in merged_hits.items():
            if ek == error_key:
                hit_info = hit
                break
        
        top_hit = {
            'error_key': error_key,
            'score': result['score'],
            'match_type': result.get('match_type', 'partial'),
            'matched_text': result.get('matched_text', '')[:200]  # Truncate
        }
        
        if hit_info:
            top_hit['candidate_count'] = len(hit_info['candidates_hit'])
            top_hit['candidates_hit'] = hit_info['candidates_hit']
            top_hit['aggregate_score'] = hit_info.get('aggregate_score', 0.0)
        
        # Add strong token info for token_overlap matches
        if top_hit['match_type'] == 'token_overlap':
            overlap_strong_count = result.get('overlap_strong_count', 0)
            overlap_strong_tokens = result.get('overlap_strong_tokens', [])
            top_hit['overlap_strong_count'] = overlap_strong_count
            top_hit['overlap_strong_tokens'] = overlap_strong_tokens[:5]  # Sample of 5
        
        debug_info['top_hits'].append(top_hit)
    
    # Route-filter fallback: if allowed_routes was applied and we got no results, try without filter
    # Only if filtering is enabled
    fallback_triggered = False
    if enable_route_filter and allowed_routes and len(merged_results) == 0:
        routes_display = allowed_routes
        if isinstance(allowed_routes, (set, list)):
            routes_display = sorted(list(set(allowed_routes)))
        logger.info(f"No results with allowed_routes={routes_display}, trying global search (fallback)")
        fallback_triggered = True
        
        # Retry with allowed_routes=None for all candidates
        for i, candidate in enumerate(query_candidates):
            candidate_name = candidate.get('name', f'candidate_{i}')
            candidate_text = candidate.get('text', '')
            candidate_weight = candidate.get('weight', 1.0)
            
            if not candidate_text:
                continue
            
            try:
                results = search_chunk_index(
                    candidate_text, 
                    index_data, 
                    allowed_routes=None,
                    enable_route_filter=enable_route_filter
                )
                
                # Merge into existing merged_hits
                for result in results:
                    error_key = result.get('error_key', 'unknown')
                    chunks = result.get('chunks', [])
                    match_type = result.get('match_type', 'partial')
                    base_score = result.get('score', 0.0)
                    matched_text = result.get('matched_text', '')
                    
                    weighted_score = base_score * candidate_weight
                    
                    for chunk in chunks:
                        chunk_id = chunk.get('chunk_id', '')
                        if not chunk_id:
                            continue
                        
                        key = (error_key, chunk_id)
                        
                        if key not in merged_hits:
                            merged_hits[key] = {
                                'error_key': error_key,
                                'chunk': chunk,
                                'match_type': match_type,
                                'matched_text': matched_text,
                                'scores': [],
                                'candidates_hit': [],
                                'aggregate_score': 0.0
                            }
                        
                        merged_hits[key]['scores'].append(weighted_score)
                        merged_hits[key]['candidates_hit'].append(candidate_name)
                        
                        current_type = merged_hits[key]['match_type']
                        type_priority = {'exact': 3, 'partial': 2, 'code_search': 1}
                        if type_priority.get(match_type, 0) > type_priority.get(current_type, 0):
                            merged_hits[key]['match_type'] = match_type
                            merged_hits[key]['matched_text'] = matched_text
            
            except Exception as e:
                logger.warning(f"Error in fallback search for candidate '{candidate_name}': {e}")
        
        # Recalculate aggregate scores after fallback
        for key, hit in merged_hits.items():
            scores = hit['scores']
            candidate_count = len(hit['candidates_hit'])
            base_agg_score = sum(scores)
            bonus = min(0.3, (candidate_count - 1) * 0.1)
            hit['aggregate_score'] = base_agg_score + bonus
        
        # Regroup results
        grouped_results = {}
        for (error_key, chunk_id), hit in merged_hits.items():
            if error_key not in grouped_results:
                grouped_results[error_key] = {
                    'error_key': error_key,
                    'chunks': [],
                    'match_type': hit['match_type'],
                    'score': hit['aggregate_score'],
                    'matched_text': hit['matched_text']
                }
            # Limit chunks per group
            MAX_CHUNKS_PER_GROUP = 3
            if len(grouped_results[error_key]['chunks']) < MAX_CHUNKS_PER_GROUP:
                grouped_results[error_key]['chunks'].append(hit['chunk'])
        
        merged_results = list(grouped_results.values())
        merged_results.sort(key=lambda x: -x['score'])
        MAX_GROUPED_RESULTS = 25
        merged_results = merged_results[:MAX_GROUPED_RESULTS]
        
        logger.info(f"Fallback search complete: {len(merged_hits)} unique hits, {len(merged_results)} grouped results")
    
    debug_info['route_filter_fallback_triggered'] = fallback_triggered
    
    logger.info(
        f"Multi-candidate search complete: {len(merged_hits)} unique hits, "
        f"{len(merged_results)} grouped results"
    )
    
    return (merged_results, debug_info)

