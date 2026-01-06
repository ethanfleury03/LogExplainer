"""
Unit tests for query candidate generation.
"""

import unittest
import sys
import os

# Add project root to path for imports
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.utils.query_candidates import build_query_candidates
from backend.utils.log_parser import parse_log_line


class TestQueryCandidates(unittest.TestCase):
    
    def test_kareela_mmcap_example(self):
        """Test candidate generation for the Kareela MMCap error line."""
        log = "2026-01-06T09:47:26.310054+11:00 RS20300529 Kareela0: <E> [#4] MMCap: localhost:9210:Dyn-ultron:LIFTER not at cap, instead at home."
        parsed = parse_log_line(log)
        
        candidates = build_query_candidates(parsed, log)
        
        # Should generate multiple candidates
        self.assertGreater(len(candidates), 0)
        
        # Extract candidate texts
        candidate_texts = [c['text'] for c in candidates]
        
        # Should include component+message version
        has_component_message = any('mmcap' in text and 'lifter' in text for text in candidate_texts)
        self.assertTrue(has_component_message, f"Should include component+message candidate. Got: {candidate_texts}")
        
        # Should include message_only version (without component)
        has_message_only = any('lifter' in text and 'not at cap' in text and 'mmcap' not in text.split()[:1] for text in candidate_texts)
        self.assertTrue(has_message_only, f"Should include message_only candidate without component prefix. Got: {candidate_texts}")
        
        # Verify route_filter is set correctly
        for cand in candidates:
            self.assertEqual(cand.get('route_filter'), 'kareela')
        
        # Verify weights are reasonable
        for cand in candidates:
            self.assertGreater(cand['weight'], 0)
            self.assertLessEqual(cand['weight'], 1.0)
    
    def test_gymea_pipe_event_example(self):
        """Test candidate generation for Gymea pipe-event line."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Gymea0: 21.3.6|unknown-PH1|event|some message"
        parsed = parse_log_line(log)
        
        candidates = build_query_candidates(parsed, log)
        
        # Should generate candidates
        self.assertGreater(len(candidates), 0)
        
        # Pipe-delimited lines should still produce candidates
        # The pipe character should be preserved or handled gracefully
        for cand in candidates:
            self.assertIsInstance(cand['text'], str)
            self.assertGreater(len(cand['text']), 0)
    
    def test_candidates_deduplication(self):
        """Test that duplicate candidates are removed."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] Test: simple message"
        parsed = parse_log_line(log)
        
        candidates = build_query_candidates(parsed, log)
        
        # Check for duplicates
        candidate_texts = [c['text'] for c in candidates]
        self.assertEqual(len(candidate_texts), len(set(candidate_texts)), "Should not have duplicate candidate texts")
    
    def test_minimum_token_requirement(self):
        """Test that candidates with <2 tokens are filtered (unless only option)."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] Test: message"
        parsed = parse_log_line(log)
        
        candidates = build_query_candidates(parsed, log)
        
        # All candidates should have at least 2 tokens (unless it's the only one)
        for cand in candidates:
            token_count = len(cand['text'].split())
            if len(candidates) > 1:
                self.assertGreaterEqual(token_count, 2, f"Candidate '{cand['name']}' should have >= 2 tokens")
    
    def test_no_component_case(self):
        """Test candidate generation when no component is present."""
        log = "Some random log message without component"
        parsed = parse_log_line(log)
        
        candidates = build_query_candidates(parsed, log)
        
        # Should still generate candidates
        if len(candidates) > 0:
            for cand in candidates:
                self.assertGreater(len(cand['text']), 0)
    
    def test_bigram_generation(self):
        """Test that bigrams are generated for longer messages."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] Component: first second third fourth fifth"
        parsed = parse_log_line(log)
        
        candidates = build_query_candidates(parsed, log)
        
        # Should have bigram candidates
        bigram_candidates = [c for c in candidates if c['name'] == 'bigram']
        self.assertGreater(len(bigram_candidates), 0, "Should generate bigram candidates for longer messages")
        
        # Each bigram should have exactly 2 tokens
        for bigram in bigram_candidates:
            tokens = bigram['text'].split()
            self.assertEqual(len(tokens), 2, f"Bigram should have 2 tokens: {bigram['text']}")


if __name__ == '__main__':
    unittest.main()

