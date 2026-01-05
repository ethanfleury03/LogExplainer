"""
Chunk index search logic.

Searches pre-indexed codebase chunks for error messages.
"""

import re
from typing import List, Dict, Any


def normalize_error_message(message: str) -> str:
    """
    Normalize error message for searching.
    
    - Lowercase
    - Strip whitespace
    - Collapse multiple whitespace to single space
    """
    if not message:
        return ""
    normalized = message.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
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


def search_chunk_index(error_message: str, index_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Search chunk-based index for error message.
    
    Strategy:
    1. Exact match only: lookup in error_index[normalized_message]
    
    Only returns results where the normalized query exactly matches an error_index key.
    No partial matching, substring matching, or token-based matching.
    
    Args:
        error_message: Error message to search for
        index_data: Full index JSON structure with 'chunks' and 'error_index'
    
    Returns:
        List of grouped results, each with error_key and chunks
    """
    if not error_message or not index_data:
        return []
    
    normalized_query = normalize_error_message(error_message)
    error_index = index_data.get('error_index', {})
    chunks_dict = {chunk['chunk_id']: chunk for chunk in index_data.get('chunks', [])}
    
    results = []
    seen_error_keys = set()
    
    # Strategy 1: Exact match only
    if normalized_query in error_index:
        for match_info in error_index[normalized_query]:
            chunk_id = match_info.get('chunk_id')
            if chunk_id and chunk_id in chunks_dict:
                error_key = match_info.get('original_message', normalized_query)
                if error_key not in seen_error_keys:
                    seen_error_keys.add(error_key)
                    chunk = chunks_dict[chunk_id]
                    # Use the error message itself as match
                    matched_text = error_key
                    results.append({
                        'error_key': error_key,
                        'chunks': [chunk],
                        'match_type': 'exact',
                        'score': 1.0,
                        'matched_text': matched_text
                    })
    
    # Sort results: exact matches only (already sorted by match_type)
    results.sort(key=lambda x: (x['match_type'] != 'exact', -x['score']))
    
    return results

