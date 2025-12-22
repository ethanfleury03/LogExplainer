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


def search_chunk_index(error_message: str, index_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Search chunk-based index for error message.
    
    Strategy:
    1. Exact match: lookup in error_index[normalized_message]
    2. Fallback: partial match over error_index keys (contains)
       - Return top 25 keys sorted by (token overlap + length proximity)
       - Then expand to chunk matches
    
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
    
    # Strategy 1: Exact match
    if normalized_query in error_index:
        for match_info in error_index[normalized_query]:
            chunk_id = match_info.get('chunk_id')
            if chunk_id and chunk_id in chunks_dict:
                error_key = match_info.get('original_message', normalized_query)
                if error_key not in seen_error_keys:
                    seen_error_keys.add(error_key)
                    results.append({
                        'error_key': error_key,
                        'chunks': [chunks_dict[chunk_id]],
                        'match_type': 'exact',
                        'score': 1.0
                    })
    
    # Strategy 2: Partial match (if no exact results or need more)
    if len(results) < 25:
        query_tokens = normalized_query.split()
        query_len = len(normalized_query)
        
        # Score all keys that contain the query
        scored_keys = []
        for error_key, match_list in error_index.items():
            if error_key in seen_error_keys:
                continue
            
            # Check if query is contained in key
            if normalized_query in error_key:
                key_tokens = error_key.split()
                key_len = len(error_key)
                
                # Calculate combined score
                token_score = _token_overlap_score(query_tokens, key_tokens)
                length_score = _length_proximity_score(query_len, key_len)
                combined_score = (token_score * 0.6) + (length_score * 0.4)
                
                scored_keys.append((error_key, combined_score, match_list))
        
        # Sort by score descending
        scored_keys.sort(key=lambda x: x[1], reverse=True)
        
        # Take top 25
        for error_key, score, match_list in scored_keys[:25]:
            if error_key in seen_error_keys:
                continue
            
            seen_error_keys.add(error_key)
            
            # Get all chunks for this error key
            chunks = []
            for match_info in match_list:
                chunk_id = match_info.get('chunk_id')
                if chunk_id and chunk_id in chunks_dict:
                    chunks.append(chunks_dict[chunk_id])
            
            if chunks:
                results.append({
                    'error_key': error_key,
                    'chunks': chunks,
                    'match_type': 'partial',
                    'score': score
                })
    
    # Sort results: exact matches first, then by score
    results.sort(key=lambda x: (x['match_type'] != 'exact', -x['score']))
    
    return results

