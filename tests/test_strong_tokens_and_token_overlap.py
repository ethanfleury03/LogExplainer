"""
Unit tests for strong token candidates and token overlap search.
"""

import unittest
import sys
import os

# Add project root to path for imports
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.utils.query_candidates import build_query_candidates, _extract_strong_tokens
from backend.utils.index_search import (
    search_chunk_index,
    search_chunk_index_multi,
    _tokenize_for_overlap,
    _token_overlap_search,
    _extract_strong_tokens as index_extract_strong_tokens
)


class TestStrongTokenCandidates(unittest.TestCase):
    
    def test_strong_token_candidates_include_result_dev_err_and_gymeamux(self):
        """Test that strong tokens like RESULT_DEV_ERR and GymeaMux are extracted."""
        # Example query line: "GymeaMux getVcs RESULT_DEV_ERR supported consumable properties"
        parsed = {
            'route': 'gymea',
            'confidence': 0.9,
            'query_text': 'gymeamux getvcs result_dev_err supported consumable properties',
            'component': None,
            'payload': 'GymeaMux getVcs RESULT_DEV_ERR supported consumable properties'
        }
        
        candidates = build_query_candidates(parsed, parsed['payload'], enable_route_filter=False)
        
        # Find strong_token candidates
        strong_token_candidates = [c for c in candidates if c['name'] == 'strong_token']
        
        self.assertGreater(len(strong_token_candidates), 0, "Should have strong token candidates")
        
        # Extract token texts
        token_texts = [c['text'] for c in strong_token_candidates]
        
        # Should include these key tokens
        self.assertIn('result_dev_err', token_texts, "Should include RESULT_DEV_ERR token")
        self.assertIn('gymeamux', token_texts, "Should include GymeaMux token")
        self.assertIn('getvcs', token_texts, "Should include getVcs token")
        
        # Should have correct weight
        for candidate in strong_token_candidates:
            self.assertEqual(candidate['weight'], 0.6, "Strong tokens should have weight 0.6")
    
    def test_extract_strong_tokens_filters_stopwords(self):
        """Test that stopwords are filtered from strong tokens."""
        query_text = "error failed attempt result_dev_err getVcs"
        payload = "ERROR failed attempt RESULT_DEV_ERR getVcs"
        
        tokens = _extract_strong_tokens(query_text, payload)
        
        # Should not include generic stopwords
        self.assertNotIn('error', tokens)
        self.assertNotIn('failed', tokens)
        self.assertNotIn('attempt', tokens)
        
        # Should include code-like tokens
        self.assertIn('result_dev_err', tokens)
        self.assertIn('getvcs', tokens)
    
    def test_extract_strong_tokens_includes_underscore_tokens(self):
        """Test that tokens with underscores are included even if short."""
        query_text = "test_result_dev_err"
        payload = "test_result_dev_err"
        
        tokens = _extract_strong_tokens(query_text, payload)
        
        # Should include underscore tokens
        self.assertIn('result_dev_err', tokens)
        self.assertIn('test_result', tokens)
    
    def test_extract_strong_tokens_includes_digit_tokens(self):
        """Test that tokens with digits are included."""
        query_text = "port9210 endpoint123"
        payload = "port9210 endpoint123"
        
        tokens = _extract_strong_tokens(query_text, payload)
        
        # Should include digit tokens
        self.assertIn('port9210', tokens)
        self.assertIn('endpoint123', tokens)
    
    def test_extract_strong_tokens_max_limit(self):
        """Test that strong tokens are capped at MAX_STRONG_TOKENS."""
        # Create a query with many tokens
        query_text = " ".join([f"token_{i}" for i in range(20)])
        payload = query_text
        
        tokens = _extract_strong_tokens(query_text, payload)
        
        # Should be limited (but check via candidate generation)
        parsed = {
            'route': 'unknown',
            'confidence': 0.5,
            'query_text': query_text,
            'component': None,
            'payload': payload
        }
        
        candidates = build_query_candidates(parsed, query_text, enable_route_filter=False)
        strong_token_candidates = [c for c in candidates if c['name'] == 'strong_token']
        
        # Should be capped at MAX_STRONG_TOKENS = 8
        self.assertLessEqual(len(strong_token_candidates), 8, "Should be capped at 8 strong tokens")


class TestTokenOverlapSearch(unittest.TestCase):
    
    def test_tokenize_for_overlap_keeps_result_dev_err_and_getvcs(self):
        """Test that tokenization keeps important tokens."""
        text = "RESULT_DEV_ERR getVcs supported consumable properties"
        
        tokens = _tokenize_for_overlap(text)
        
        # Should include underscore and CamelCase tokens
        self.assertIn('result_dev_err', tokens)
        self.assertIn('getvcs', tokens)
        self.assertIn('supported', tokens)
        self.assertIn('consumable', tokens)
        self.assertIn('properties', tokens)
        
        # Should not include stopwords
        self.assertNotIn('error', tokens)
    
    def test_tokenize_for_overlap_filters_short_tokens(self):
        """Test that short tokens without special chars are filtered."""
        text = "a the an it error RESULT_DEV_ERR"
        
        tokens = _tokenize_for_overlap(text)
        
        # Should filter out short stopwords
        self.assertNotIn('a', tokens)
        self.assertNotIn('the', tokens)
        self.assertNotIn('an', tokens)
        self.assertNotIn('it', tokens)
        
        # Should keep underscore tokens even if short parts
        self.assertIn('result_dev_err', tokens)
    
    def test_token_overlap_search_finds_chunks_when_overlap_ge_k(self):
        """Test token overlap search finds chunks when overlap >= min_hits."""
        # Create fake chunks with code containing relevant tokens
        chunks_dict = {
            'chunk1': {
                'chunk_id': 'chunk1',
                'file_path': '/test/file1.py',
                'function_name': 'test_func1',
                'code': 'def test_func1():\n    supported = True\n    consumable = "cyan"\n    properties = {}',
                'signature': 'def test_func1()',
                'docstring': '',
                'leading_comment': '',
                'error_messages': []
            },
            'chunk2': {
                'chunk_id': 'chunk2',
                'file_path': '/test/file2.py',
                'function_name': 'test_func2',
                'code': 'def test_func2():\n    result = getVcs()',
                'signature': 'def test_func2()',
                'docstring': '',
                'leading_comment': '',
                'error_messages': []
            },
            'chunk3': {
                'chunk_id': 'chunk3',
                'file_path': '/test/file3.py',
                'function_name': 'test_func3',
                'code': 'def test_func3():\n    pass',
                'signature': 'def test_func3()',
                'docstring': '',
                'leading_comment': '',
                'error_messages': []
            }
        }
        
        seen_chunk_ids = set()
        seen_error_keys = set()
        
        # Search for "supported consumable properties" - should find chunk1 (3 token overlap)
        candidate_text = "supported consumable properties"
        results = _token_overlap_search(
            candidate_text,
            chunks_dict,
            seen_chunk_ids,
            seen_error_keys
        )
        
        # Should find chunk1 (has all 3 tokens)
        result_chunk_ids = {chunk['chunk_id'] for result in results for chunk in result['chunks']}
        self.assertIn('chunk1', result_chunk_ids, "Should find chunk with overlapping tokens")
        
        # Check match_type
        for result in results:
            if any(chunk['chunk_id'] == 'chunk1' for chunk in result['chunks']):
                self.assertEqual(result['match_type'], 'token_overlap')
                self.assertIn('overlap:', result['matched_text'])
        
        # Search for "getvcs" - should find chunk2 (1 token, min_hits=1 for single token)
        seen_chunk_ids = set()
        seen_error_keys = set()
        results2 = _token_overlap_search(
            "getvcs",
            chunks_dict,
            seen_chunk_ids,
            seen_error_keys
        )
        
        result_chunk_ids2 = {chunk['chunk_id'] for result in results2 for chunk in result['chunks']}
        self.assertIn('chunk2', result_chunk_ids2, "Should find chunk with getvcs token")
    
    def test_token_overlap_search_respects_min_hits(self):
        """Test that token overlap search respects min_hits threshold."""
        chunks_dict = {
            'chunk1': {
                'chunk_id': 'chunk1',
                'file_path': '/test/file1.py',
                'function_name': 'test_func1',
                'code': 'supported',  # Only 1 token
                'signature': '',
                'docstring': '',
                'leading_comment': '',
                'error_messages': []
            }
        }
        
        seen_chunk_ids = set()
        seen_error_keys = set()
        
        # Search for "supported consumable properties" (3 tokens, min_hits=2)
        # chunk1 only has 1 token, so should NOT match
        results = _token_overlap_search(
            "supported consumable properties",
            chunks_dict,
            seen_chunk_ids,
            seen_error_keys
        )
        
        result_chunk_ids = {chunk['chunk_id'] for result in results for chunk in result['chunks']}
        self.assertNotIn('chunk1', result_chunk_ids, "Should not match with overlap < min_hits")
        
        # But single token query should match (min_hits=1)
        seen_chunk_ids = set()
        seen_error_keys = set()
        results2 = _token_overlap_search(
            "supported",
            chunks_dict,
            seen_chunk_ids,
            seen_error_keys
        )
        
        result_chunk_ids2 = {chunk['chunk_id'] for result in results2 for chunk in result['chunks']}
        self.assertIn('chunk1', result_chunk_ids2, "Should match single token with min_hits=1")
    
    def test_search_chunk_index_multi_always_has_match_counts(self):
        """Regression test: verify match_counts is always defined in candidate stats."""
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'chunk1',
                    'route': 'unknown',
                    'file_path': '/test/file1.py',
                    'function_name': 'test_func',
                    'code': 'def test_func(): pass',
                    'error_messages': []
                }
            ],
            'error_index': {}
        }
        
        candidates = [
            {
                'name': 'test_candidate',
                'text': 'def test_func',
                'weight': 1.0,
                'allowed_routes': None
            }
        ]
        
        results, debug_info = search_chunk_index_multi(
            candidates,
            index_data,
            allowed_routes=None,
            enable_route_filter=False
        )
        
        # Verify candidate stats exist and have match_counts
        self.assertIn('candidates', debug_info)
        self.assertGreater(len(debug_info['candidates']), 0)
        
        for stat in debug_info['candidates']:
            # Every stat should have match_counts (never missing)
            self.assertIn('match_counts', stat, "Candidate stat must have match_counts")
            match_counts = stat['match_counts']
            # Verify it has expected keys
            self.assertIn('exact', match_counts)
            self.assertIn('partial', match_counts)
            self.assertIn('code_search', match_counts)
            self.assertIn('token_overlap', match_counts)
            
            # Verify values are integers
            for key in ['exact', 'partial', 'code_search', 'token_overlap']:
                self.assertIsInstance(match_counts[key], int, 
                                    f"match_counts['{key}'] should be int")
    
    def test_generic_tokens_no_longer_flood_results(self):
        """Test that queries with generic tokens don't return 25 token_overlap hits."""
        # Create index with chunks that would match generic tokens
        index_data = {
            'chunks': [
                {
                    'chunk_id': f'chunk{i}',
                    'route': 'unknown',
                    'file_path': f'/test/file{i}.py',
                    'function_name': f'test_func{i}',
                    'code': f'def test_func{i}():\n    error = True\n    check = False\n    result = None',
                    'error_messages': []
                }
                for i in range(30)  # Many chunks with generic tokens
            ],
            'error_index': {}
        }
        
        # Query with only generic tokens (should be filtered by stopwords and strong token gating)
        candidates = [
            {
                'name': 'generic_query',
                'text': 'error check result',
                'weight': 1.0,
                'allowed_routes': None
            }
        ]
        
        results, debug_info = search_chunk_index_multi(
            candidates,
            index_data,
            allowed_routes=None,
            enable_route_filter=False
        )
        
        # Should NOT return 25 token_overlap results (gating should filter most)
        token_overlap_count = sum(1 for r in results if r.get('match_type') == 'token_overlap')
        self.assertLess(token_overlap_count, 25, 
                       "Generic token queries should not flood results with token_overlap")
    
    def test_strong_token_query_prefers_relevant_chunks(self):
        """Test that query with RESULT_DEV_ERR and getvcs prefers chunks containing those tokens."""
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'relevant_chunk',
                    'route': 'unknown',
                    'file_path': '/test/relevant.py',
                    'function_name': 'handle_result_dev_err',
                    'code': 'def handle_result_dev_err():\n    result = getVcs()\n    if result == RESULT_DEV_ERR:\n        pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'generic_chunk',
                    'route': 'unknown',
                    'file_path': '/test/generic.py',
                    'function_name': 'generic_func',
                    'code': 'def generic_func():\n    error = True\n    check = False',
                    'error_messages': []
                }
            ],
            'error_index': {}
        }
        
        # Query with strong tokens
        candidates = [
            {
                'name': 'strong_token_query',
                'text': 'RESULT_DEV_ERR getVcs',
                'weight': 1.0,
                'allowed_routes': None
            }
        ]
        
        results, debug_info = search_chunk_index_multi(
            candidates,
            index_data,
            allowed_routes=None,
            enable_route_filter=False
        )
        
        # Should find the relevant chunk (has both strong tokens)
        result_chunk_ids = set()
        for result in results:
            for chunk in result.get('chunks', []):
                result_chunk_ids.add(chunk.get('chunk_id'))
        
        self.assertIn('relevant_chunk', result_chunk_ids, 
                     "Should find chunk with strong tokens RESULT_DEV_ERR and getvcs")
        
        # Relevant chunk should rank higher (if token_overlap is used)
        relevant_result = None
        for result in results:
            for chunk in result.get('chunks', []):
                if chunk.get('chunk_id') == 'relevant_chunk':
                    relevant_result = result
                    break
        
        if relevant_result:
            # Should have strong token overlap
            if relevant_result.get('match_type') == 'token_overlap':
                overlap_strong_count = relevant_result.get('overlap_strong_count', 0)
                self.assertGreaterEqual(overlap_strong_count, 1,
                                       "Relevant chunk should have strong token overlap")
    
    def test_exact_partial_outrank_token_overlap(self):
        """Test that exact/partial matches outrank token_overlap in scoring."""
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'exact_match',
                    'route': 'unknown',
                    'file_path': '/test/exact.py',
                    'function_name': 'exact_func',
                    'code': 'def exact_func(): pass',
                    'error_messages': [
                        {'message': 'RESULT_DEV_ERR getVcs'}
                    ]
                },
                {
                    'chunk_id': 'token_overlap_match',
                    'route': 'unknown',
                    'file_path': '/test/overlap.py',
                    'function_name': 'overlap_func',
                    'code': 'def overlap_func():\n    result_dev_err = True\n    getvcs = False',
                    'error_messages': []
                }
            ],
            'error_index': {
                'result_dev_err getvcs': [
                    {
                        'chunk_id': 'exact_match',
                        'original_message': 'RESULT_DEV_ERR getVcs'
                    }
                ]
            }
        }
        
        # Query that matches both
        candidates = [
            {
                'name': 'test_query',
                'text': 'RESULT_DEV_ERR getVcs',
                'weight': 1.0,
                'allowed_routes': None
            }
        ]
        
        results, debug_info = search_chunk_index_multi(
            candidates,
            index_data,
            allowed_routes=None,
            enable_route_filter=False
        )
        
        # Exact/partial should rank higher than token_overlap
        if len(results) >= 2:
            first_type = results[0].get('match_type')
            # First result should be exact or partial, not token_overlap
            self.assertIn(first_type, ('exact', 'partial'),
                         "Exact/partial matches should rank above token_overlap")
            
            # Check scores (exact/partial should have higher scores due to 4.0x boost)
            first_score = results[0].get('score', 0)
            for result in results[1:]:
                if result.get('match_type') == 'token_overlap':
                    overlap_score = result.get('score', 0)
                    # Exact/partial with 4.0x boost should be much higher than token_overlap (max 0.6)
                    if first_type in ('exact', 'partial'):
                        self.assertGreater(first_score, overlap_score,
                                         "Exact/partial scores (4.0x) should be higher than token_overlap")


if __name__ == '__main__':
    unittest.main()

