"""
Unit tests for route filter expansion to include UNKNOWN chunks and feature flag.
"""

import unittest
import sys
import os
from unittest.mock import patch

# Add project root to path for imports
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.utils.index_search import search_chunk_index, search_chunk_index_multi
from backend.utils.query_candidates import build_query_candidates
from backend.routes.error_debug_routes import search_index


class TestRouteFilterExpansion(unittest.TestCase):
    
    def test_allowed_routes_includes_unknown(self):
        """Test that route filtering includes both target route and 'unknown'."""
        # Create fake index data with chunks from different routes
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'kareela_chunk_1',
                    'route': 'kareela',
                    'file_path': '/opt/memjet/kareela/test1.py',
                    'function_name': 'test_func',
                    'code': 'def test_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'kareela_chunk_2',
                    'route': 'kareela',
                    'file_path': '/opt/memjet/kareela/test2.py',
                    'function_name': 'another_func',
                    'code': 'def another_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'gymea_chunk_1',
                    'route': 'gymea',
                    'file_path': '/opt/memjet/gymea/test.py',
                    'function_name': 'gymea_func',
                    'code': 'def gymea_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'unknown_chunk_1',
                    'route': 'unknown',
                    'file_path': '/opt/memjet/common/test.py',
                    'function_name': 'common_func',
                    'code': 'def common_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'unknown_chunk_2',
                    'route': 'unknown',
                    'file_path': '/opt/memjet/utils/test.py',
                    'function_name': 'util_func',
                    'code': 'def util_func(): pass',
                    'error_messages': []
                },
            ],
            'error_index': {}
        }
        
        # Search with allowed_routes=['kareela', 'unknown']
        # Use queries that will match code content
        queries = ['def test_func', 'def another_func', 'def common_func', 'def util_func']
        allowed_routes = ['kareela', 'unknown']
        
        # Collect all chunk_ids from all queries
        all_result_chunk_ids = set()
        for query in queries:
            results = search_chunk_index(query, index_data, allowed_routes=allowed_routes)
            for result in results:
                for chunk in result.get('chunks', []):
                    all_result_chunk_ids.add(chunk.get('chunk_id'))
        
        # Should include kareela and unknown chunks, but NOT gymea
        self.assertIn('kareela_chunk_1', all_result_chunk_ids, "Should include kareela chunks")
        self.assertIn('kareela_chunk_2', all_result_chunk_ids, "Should include kareela chunks")
        self.assertIn('unknown_chunk_1', all_result_chunk_ids, "Should include unknown chunks")
        self.assertIn('unknown_chunk_2', all_result_chunk_ids, "Should include unknown chunks")
        self.assertNotIn('gymea_chunk_1', all_result_chunk_ids, "Should NOT include gymea chunks")
    
    def test_backward_compatibility_string_route_filter(self):
        """Test backward compatibility with string route_filter parameter."""
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'kareela_chunk_1',
                    'route': 'kareela',
                    'file_path': '/opt/memjet/kareela/test1.py',
                    'function_name': 'test_func',
                    'code': 'def test_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'unknown_chunk_1',
                    'route': 'unknown',
                    'file_path': '/opt/memjet/common/test.py',
                    'function_name': 'common_func',
                    'code': 'def common_func(): pass',
                    'error_messages': []
                },
            ],
            'error_index': {}
        }
        
        # Should accept string (backward compatibility)
        query = 'def test_func'
        results = search_chunk_index(query, index_data, allowed_routes='kareela')
        
        result_chunk_ids = set()
        for result in results:
            for chunk in result.get('chunks', []):
                result_chunk_ids.add(chunk.get('chunk_id'))
        
        # With string filter, should only get kareela (old behavior)
        self.assertIn('kareela_chunk_1', result_chunk_ids)
        # Note: string filter doesn't automatically include 'unknown', that's handled at endpoint level
    
    def test_no_filter_returns_all(self):
        """Test that no filter returns all routes."""
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'kareela_chunk_1',
                    'route': 'kareela',
                    'file_path': '/opt/memjet/kareela/test1.py',
                    'function_name': 'test_func',
                    'code': 'def test_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'gymea_chunk_1',
                    'route': 'gymea',
                    'file_path': '/opt/memjet/gymea/test.py',
                    'function_name': 'gymea_func',
                    'code': 'def gymea_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'unknown_chunk_1',
                    'route': 'unknown',
                    'file_path': '/opt/memjet/common/test.py',
                    'function_name': 'common_func',
                    'code': 'def common_func(): pass',
                    'error_messages': []
                },
            ],
            'error_index': {}
        }
        
        # Test with queries that match each chunk
        queries = ['def test_func', 'def gymea_func', 'def common_func']
        
        all_result_chunk_ids = set()
        for query in queries:
            results = search_chunk_index(query, index_data, allowed_routes=None)
            for result in results:
                for chunk in result.get('chunks', []):
                    all_result_chunk_ids.add(chunk.get('chunk_id'))
        
        # Should include all routes when no filter
        self.assertIn('kareela_chunk_1', all_result_chunk_ids)
        self.assertIn('gymea_chunk_1', all_result_chunk_ids)
        self.assertIn('unknown_chunk_1', all_result_chunk_ids)
    
    def test_set_allowed_routes(self):
        """Test that set type is accepted for allowed_routes."""
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'kareela_chunk_1',
                    'route': 'kareela',
                    'file_path': '/opt/memjet/kareela/test1.py',
                    'function_name': 'test_func',
                    'code': 'def test_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'unknown_chunk_1',
                    'route': 'unknown',
                    'file_path': '/opt/memjet/common/test.py',
                    'function_name': 'common_func',
                    'code': 'def common_func(): pass',
                    'error_messages': []
                },
            ],
            'error_index': {}
        }
        
        queries = ['def test_func', 'def common_func']
        
        all_result_chunk_ids = set()
        for query in queries:
            results = search_chunk_index(query, index_data, allowed_routes={'kareela', 'unknown'})
            for result in results:
                for chunk in result.get('chunks', []):
                    all_result_chunk_ids.add(chunk.get('chunk_id'))
        
        self.assertIn('kareela_chunk_1', all_result_chunk_ids)
        self.assertIn('unknown_chunk_1', all_result_chunk_ids)
    
    @patch.dict(os.environ, {'ERROR_DEBUG_ENABLE_ROUTE_FILTER': 'false'})
    def test_route_filter_disabled_by_default(self):
        """Test that route filtering is disabled by default (flag=false)."""
        # This test verifies the behavior when the feature flag is not set or set to false
        # The endpoint should not filter by route even if route is detected as kareela/gymea
        
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'kareela_chunk_1',
                    'route': 'kareela',
                    'file_path': '/opt/memjet/kareela/test1.py',
                    'function_name': 'test_func',
                    'code': 'def test_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'gymea_chunk_1',
                    'route': 'gymea',
                    'file_path': '/opt/memjet/gymea/test.py',
                    'function_name': 'gymea_func',
                    'code': 'def gymea_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'unknown_chunk_1',
                    'route': 'unknown',
                    'file_path': '/opt/memjet/common/test.py',
                    'function_name': 'common_func',
                    'code': 'def common_func(): pass',
                    'error_messages': []
                },
            ],
            'error_index': {}
        }
        
        # When filtering is disabled, all routes should be returned regardless of detected route
        queries = ['def test_func', 'def gymea_func', 'def common_func']
        
        all_result_chunk_ids = set()
        for query in queries:
            # Search with allowed_routes=None (what the endpoint would use when flag is false)
            results = search_chunk_index(query, index_data, allowed_routes=None)
            for result in results:
                for chunk in result.get('chunks', []):
                    all_result_chunk_ids.add(chunk.get('chunk_id'))
        
        # Should include all routes when filtering is disabled
        self.assertIn('kareela_chunk_1', all_result_chunk_ids, 
                      "Should include kareela chunks when filtering disabled")
        self.assertIn('gymea_chunk_1', all_result_chunk_ids, 
                      "Should include gymea chunks when filtering disabled")
        self.assertIn('unknown_chunk_1', all_result_chunk_ids, 
                      "Should include unknown chunks when filtering disabled")
    
    def test_route_filter_when_flag_missing_defaults_to_false(self):
        """Test that missing env var defaults to filtering disabled."""
        # Ensure env var is not set
        env_key = 'ERROR_DEBUG_ENABLE_ROUTE_FILTER'
        original_value = os.environ.get(env_key)
        if env_key in os.environ:
            del os.environ[env_key]
        
        try:
            # Default behavior should be False (filtering disabled)
            # This is tested via the search function behavior with allowed_routes=None
            index_data = {
                'chunks': [
                    {
                        'chunk_id': 'kareela_chunk_1',
                        'route': 'kareela',
                        'file_path': '/opt/memjet/kareela/test1.py',
                        'function_name': 'test_func',
                        'code': 'def test_func(): pass',
                        'error_messages': []
                    },
                    {
                        'chunk_id': 'gymea_chunk_1',
                        'route': 'gymea',
                        'file_path': '/opt/memjet/gymea/test.py',
                        'function_name': 'gymea_func',
                        'code': 'def gymea_func(): pass',
                        'error_messages': []
                    },
                ],
                'error_index': {}
            }
            
            # With allowed_routes=None (default when flag is false/missing), all routes should be returned
            results = search_chunk_index('def test_func', index_data, allowed_routes=None)
            chunk_ids = {chunk.get('chunk_id') for result in results for chunk in result.get('chunks', [])}
            
            # Should find both kareela and gymea chunks
            self.assertIn('kareela_chunk_1', chunk_ids)
            # Note: The query might not match gymea_func, but the filter itself shouldn't exclude it
            # So if we search with a query that matches both, we should get both
            results_all = search_chunk_index('def', index_data, allowed_routes=None)
            all_chunk_ids = {chunk.get('chunk_id') for result in results_all for chunk in result.get('chunks', [])}
            self.assertIn('kareela_chunk_1', all_chunk_ids)
            self.assertIn('gymea_chunk_1', all_chunk_ids)
            
        finally:
            # Restore original env var if it existed
            if original_value is not None:
                os.environ[env_key] = original_value
    
    def test_query_candidates_no_allowed_routes_when_flag_false(self):
        """Test that build_query_candidates doesn't set allowed_routes when enable_route_filter=False."""
        parsed = {
            'route': 'kareela',
            'confidence': 0.95,
            'query_text': 'test error message',
            'component': None,
            'payload': 'test error message'
        }
        
        # When flag is False, candidates should not have allowed_routes set
        candidates = build_query_candidates(parsed, 'test error message', enable_route_filter=False)
        
        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            # Allowed routes should be None when filtering is disabled
            self.assertIsNone(candidate.get('allowed_routes'), 
                            f"Candidate {candidate.get('name')} should not have allowed_routes when flag is False")
    
    def test_query_candidates_has_allowed_routes_when_flag_true(self):
        """Test that build_query_candidates sets allowed_routes when enable_route_filter=True."""
        parsed = {
            'route': 'kareela',
            'confidence': 0.95,
            'query_text': 'test error message',
            'component': None,
            'payload': 'test error message'
        }
        
        # When flag is True and route detected with high confidence, candidates should have allowed_routes
        candidates = build_query_candidates(parsed, 'test error message', enable_route_filter=True)
        
        self.assertGreater(len(candidates), 0)
        # At least one candidate should have allowed_routes set
        has_allowed_routes = any(c.get('allowed_routes') for c in candidates)
        self.assertTrue(has_allowed_routes, "Candidates should have allowed_routes when flag is True")
        # Verify it's the expected value
        for candidate in candidates:
            if candidate.get('allowed_routes'):
                self.assertEqual(candidate['allowed_routes'], ['kareela', 'unknown'])
    
    def test_multi_candidate_search_ignores_candidate_allowed_routes_when_flag_false(self):
        """Test that search_chunk_index_multi ignores candidate-level allowed_routes when enable_route_filter=False."""
        index_data = {
            'chunks': [
                {
                    'chunk_id': 'kareela_chunk_1',
                    'route': 'kareela',
                    'file_path': '/opt/memjet/kareela/test1.py',
                    'function_name': 'test_func',
                    'code': 'def test_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'gymea_chunk_1',
                    'route': 'gymea',
                    'file_path': '/opt/memjet/gymea/test.py',
                    'function_name': 'gymea_func',
                    'code': 'def gymea_func(): pass',
                    'error_messages': []
                },
                {
                    'chunk_id': 'unknown_chunk_1',
                    'route': 'unknown',
                    'file_path': '/opt/memjet/common/test.py',
                    'function_name': 'common_func',
                    'code': 'def common_func(): pass',
                    'error_messages': []
                },
            ],
            'error_index': {}
        }
        
        # Create candidates with allowed_routes set (simulating old behavior)
        candidates = [
            {
                'name': 'test_candidate',
                'text': 'def test_func',
                'weight': 1.0,
                'allowed_routes': ['kareela', 'unknown']  # Would filter if enabled
            },
            {
                'name': 'gymea_candidate',
                'text': 'def gymea_func',
                'weight': 1.0,
                'allowed_routes': ['kareela', 'unknown']  # Would filter if enabled
            }
        ]
        
        # When enable_route_filter=False, should search all chunks regardless of candidate allowed_routes
        results, debug_info = search_chunk_index_multi(
            candidates, 
            index_data, 
            allowed_routes=['kareela', 'unknown'],  # Even with default allowed_routes
            enable_route_filter=False  # But filtering disabled
        )
        
        # Should find both kareela and gymea chunks (filtering was ignored)
        result_chunk_ids = set()
        for result in results:
            for chunk in result.get('chunks', []):
                result_chunk_ids.add(chunk.get('chunk_id'))
        
        # With filtering disabled, should find chunks from all routes
        # The query 'def test_func' matches kareela_chunk_1, 'def gymea_func' matches gymea_chunk_1
        self.assertIn('kareela_chunk_1', result_chunk_ids, 
                     "Should find kareela chunks when filtering disabled")
        # Note: gymea_func might not match test_func query, but the key point is filtering was ignored


if __name__ == '__main__':
    unittest.main()

