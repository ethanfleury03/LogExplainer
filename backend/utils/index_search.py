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
                    chunk = chunks_dict[chunk_id]
                    # Extract match excerpt from error message or code
                    matched_text = error_key  # Use the error message itself as match
                    if not matched_text:
                        # Fallback to code excerpt
                        matched_text = _extract_match_excerpt(error_message, chunk.get('code', ''))
                    results.append({
                        'error_key': error_key,
                        'chunks': [chunk],
                        'match_type': 'exact',
                        'score': 1.0,
                        'matched_text': matched_text
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
                # Extract match excerpt from the first chunk's error message or code
                matched_text = error_key  # Use the error key as match
                if chunks:
                    chunk = chunks[0]
                    # Try to find better excerpt in code if error_key is too generic
                    code_excerpt = _extract_match_excerpt(error_message, chunk.get('code', ''))
                    if code_excerpt and len(code_excerpt) > len(matched_text):
                        matched_text = code_excerpt
                results.append({
                    'error_key': error_key,
                    'chunks': chunks,
                    'match_type': 'partial',
                    'score': score,
                    'matched_text': matched_text
                })
    
    # Strategy 3: Code content search (if no results from error_index)
    if not results:
        normalized_query = normalize_error_message(error_message)
        query_lower = normalized_query.lower()
        
        # Filter to significant tokens only
        query_tokens = _filter_significant_tokens(query_lower.split())
        
        # Require at least 2 significant tokens for code search
        if len(query_tokens) < 2:
            return results
        
        # Search within chunk code content with improved scoring
        scored_chunks = []
        for chunk in index_data.get('chunks', []):
            code = chunk.get('code', '').lower()
            signature = chunk.get('signature', '').lower()
            docstring = (chunk.get('docstring', '') or '').lower()
            leading_comment = (chunk.get('leading_comment', '') or '').lower()
            error_messages = [e.get('message', '').lower() for e in chunk.get('error_messages', [])]
            
            # Priority 1: Check error messages in chunk (highest relevance)
            error_msg_score = 0.0
            for error_msg in error_messages:
                if error_msg:
                    error_msg_score = max(error_msg_score, _calculate_phrase_match_score(normalized_query, error_msg))
            
            # Priority 2: Check code content
            code_score = _calculate_phrase_match_score(normalized_query, code)
            
            # Priority 3: Check docstring and comments (lower relevance)
            doc_score = _calculate_phrase_match_score(normalized_query, docstring + ' ' + leading_comment)
            
            # Combined score with weights
            # Error messages get highest weight, then code, then docs
            if error_msg_score > 0:
                score = error_msg_score * 1.0  # Full weight for error message matches
            elif code_score > 0:
                score = code_score * 0.8  # Slightly lower for code matches
            elif doc_score > 0:
                score = doc_score * 0.5  # Lower for doc/comment matches
            else:
                score = 0.0
            
            # Only include chunks with meaningful matches (score >= 0.3)
            if score >= 0.3:
                scored_chunks.append((chunk, score))
        
        # Sort by score and take top 25
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        if scored_chunks:
            # Group by file_path for cleaner results
            file_groups = {}
            for chunk, score in scored_chunks[:25]:
                file_path = chunk.get('file_path', 'unknown')
                if file_path not in file_groups:
                    file_groups[file_path] = []
                file_groups[file_path].append((chunk, score))
            
            # Create results grouped by file, only include top scoring files
            sorted_files = sorted(file_groups.items(), key=lambda x: max(c[1] for c in x[1]), reverse=True)
            for file_path, chunk_scores in sorted_files[:10]:  # Top 10 files by max score
                chunks = [c[0] for c in chunk_scores]
                max_score = max(c[1] for c in chunk_scores)
                # Extract match excerpt from the best matching chunk
                best_chunk = max(chunk_scores, key=lambda x: x[1])[0]
                matched_text = ""
                # Try error messages first
                for error_msg in best_chunk.get('error_messages', []):
                    msg = error_msg.get('message', '')
                    if normalized_query.lower() in msg.lower():
                        matched_text = msg
                        break
                # Fallback to code excerpt
                if not matched_text:
                    matched_text = _extract_match_excerpt(error_message, best_chunk.get('code', ''))
                # If still no match, use a snippet from code
                if not matched_text and best_chunk.get('code'):
                    code = best_chunk.get('code', '')
                    if len(code) > 150:
                        matched_text = code[:150] + '...'
                    else:
                        matched_text = code
                results.append({
                    'error_key': f"Code match in {file_path}",
                    'chunks': chunks,
                    'match_type': 'code_search',
                    'score': max_score,
                    'matched_text': matched_text
                })
    
    # Sort results: exact matches first, then by score
    results.sort(key=lambda x: (x['match_type'] != 'exact', -x['score']))
    
    return results

