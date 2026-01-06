"""
Chunk index search logic.

Searches pre-indexed codebase chunks for error messages.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


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
    route_filter: Optional[str] = None
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
        route_filter: Optional route to filter by ("kareela" | "gymea")
    
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
    
    # Apply route filter if provided
    if route_filter:
        original_count = len(chunks_dict)
        chunks_dict = {
            cid: chunk for cid, chunk in chunks_dict.items()
            if chunk.get('route') == route_filter
        }
        logger.debug(
            f"Route filter applied: {route_filter}, "
            f"{len(chunks_dict)}/{original_count} chunks remain"
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
                            'score': 1.0,
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
                            'score': phrase_score,
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
                    'score': 0.6,  # Lower score for code matches
                    'matched_text': matched_text
                })
    
    # Sort results: exact matches first, then partial, then code_search, all by score
    results.sort(key=lambda x: (
        x['match_type'] != 'exact',  # exact first
        x['match_type'] == 'code_search',  # code_search last
        -x['score']  # then by score descending
    ))
    
    # Limit total results to top 50 to avoid overwhelming the UI
    # User can refine search if needed
    return results[:50]


def search_chunk_index_multi(
    query_candidates: List[Dict[str, Any]],
    index_data: Dict[str, Any],
    route_filter: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Search using multiple query candidates and merge results.
    
    Args:
        query_candidates: List of candidate dicts with 'name', 'text', 'weight', 'route_filter'
        index_data: Full index JSON structure
        route_filter: Optional default route filter (can be overridden per candidate)
    
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
    
    # Search each candidate
    for i, candidate in enumerate(query_candidates):
        candidate_name = candidate.get('name', f'candidate_{i}')
        candidate_text = candidate.get('text', '')
        candidate_weight = candidate.get('weight', 1.0)
        candidate_route_filter = candidate.get('route_filter') or route_filter
        
        if not candidate_text:
            continue
        
        logger.debug(f"Searching candidate {i+1}/{len(query_candidates)}: {candidate_name} = '{candidate_text[:60]}...'")
        
        try:
            # Search with this candidate
            results = search_chunk_index(candidate_text, index_data, route_filter=candidate_route_filter)
            
            # Count match types
            match_counts = {'exact': 0, 'partial': 0, 'code_search': 0}
            for r in results:
                match_type = r.get('match_type', 'partial')
                match_counts[match_type] = match_counts.get(match_type, 0) + 1
            
            candidate_stat = {
                'name': candidate_name,
                'text': candidate_text,
                'weight': candidate_weight,
                'route_filter': candidate_route_filter,
                'total_results': len(results),
                'match_counts': match_counts
            }
            candidate_stats.append(candidate_stat)
            
            logger.debug(
                f"Candidate '{candidate_name}': {len(results)} results "
                f"(exact:{match_counts['exact']}/partial:{match_counts['partial']}/code:{match_counts['code_search']})"
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
                    
                    # Update match_type to best (exact > partial > code_search)
                    current_type = merged_hits[key]['match_type']
                    type_priority = {'exact': 3, 'partial': 2, 'code_search': 1}
                    if type_priority.get(match_type, 0) > type_priority.get(current_type, 0):
                        merged_hits[key]['match_type'] = match_type
                        merged_hits[key]['matched_text'] = matched_text
        
        except Exception as e:
            logger.warning(f"Error searching candidate '{candidate_name}': {e}", exc_info=True)
            candidate_stats.append({
                'name': candidate_name,
                'text': candidate_text,
                'error': str(e)
            })
    
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
        
        grouped_results[error_key]['chunks'].append(hit['chunk'])
    
    # Convert to list and sort by aggregate score (descending)
    merged_results = list(grouped_results.values())
    merged_results.sort(key=lambda x: -x['score'])
    
    # Limit to top 50
    merged_results = merged_results[:50]
    
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
            'match_type': result['match_type']
        }
        
        if hit_info:
            top_hit['candidate_count'] = len(hit_info['candidates_hit'])
            top_hit['candidates_hit'] = hit_info['candidates_hit']
        
        debug_info['top_hits'].append(top_hit)
    
    # Route-filter fallback: if route_filter was applied and we got no results, try without filter
    fallback_triggered = False
    if route_filter and len(merged_results) == 0:
        logger.info(f"No results with route_filter={route_filter}, trying global search (fallback)")
        fallback_triggered = True
        
        # Retry with route_filter=None for all candidates
        for i, candidate in enumerate(query_candidates):
            candidate_name = candidate.get('name', f'candidate_{i}')
            candidate_text = candidate.get('text', '')
            candidate_weight = candidate.get('weight', 1.0)
            
            if not candidate_text:
                continue
            
            try:
                results = search_chunk_index(candidate_text, index_data, route_filter=None)
                
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
            grouped_results[error_key]['chunks'].append(hit['chunk'])
        
        merged_results = list(grouped_results.values())
        merged_results.sort(key=lambda x: -x['score'])
        merged_results = merged_results[:50]
        
        logger.info(f"Fallback search complete: {len(merged_hits)} unique hits, {len(merged_results)} grouped results")
    
    debug_info['route_filter_fallback_triggered'] = fallback_triggered
    
    logger.info(
        f"Multi-candidate search complete: {len(merged_hits)} unique hits, "
        f"{len(merged_results)} grouped results"
    )
    
    return (merged_results, debug_info)

