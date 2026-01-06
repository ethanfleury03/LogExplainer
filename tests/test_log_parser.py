"""
Unit tests for log parser module.
"""

import unittest
import sys
import os

# Add project root to path for imports
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.utils.log_parser import parse_log_line


class TestLogParser(unittest.TestCase):
    
    def test_kareela_example_1(self):
        """Test the provided Kareela error example."""
        log = "2026-01-06T09:47:26.310054+11:00 RS20300529 Kareela0: <E> [#4] MMCap: localhost:9210:Dyn-ultron:LIFTER not at cap, instead at home."
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'kareela')
        self.assertGreaterEqual(result['confidence'], 0.8)
        self.assertIn('MMCap:', result['payload'])
        # Query text should contain component and message, but not transport prefixes
        self.assertIn('mmcap', result['query_text'])
        self.assertIn('lifter', result['query_text'])
        self.assertIn('not at cap', result['query_text'])
        self.assertNotIn('localhost', result['query_text'])
        self.assertNotIn('9210', result['query_text'])
        self.assertEqual(result['severity'], 'E')
        self.assertEqual(result['tag'], '4')
        self.assertEqual(result['component'], 'MMCap')
    
    def test_kareela_example_2(self):
        """Test Kareela PeriodicIdle example."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'kareela')
        self.assertGreaterEqual(result['confidence'], 0.8)
        self.assertIn('PeriodicIdle', result['payload'])
        # Query text should contain component and message
        self.assertIn('periodicidle', result['query_text'])
        self.assertIn('valve', result['query_text'])
        self.assertNotIn('localhost:9210', result['query_text'])
        self.assertEqual(result['severity'], 'E')
        self.assertEqual(result['tag'], '4')
        self.assertEqual(result['component'], 'PeriodicIdle')
    
    def test_kareela_info_example(self):
        """Test Kareela info line."""
        log = "2025-12-19T05:22:06.751222+11:00 RS20300529 Kareela0: <I> [#4] EngineConductor: Changing state from EngineConductor::State::IDLE to EngineConductor::State::SERVICING on periodic idle maint"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'kareela')
        self.assertGreaterEqual(result['confidence'], 0.8)
        self.assertIn('EngineConductor', result['payload'])
        self.assertIn('engineconductor', result['query_text'])
        self.assertIn('changing state', result['query_text'])
        self.assertEqual(result['severity'], 'I')
        self.assertEqual(result['tag'], '4')
        self.assertEqual(result['component'], 'EngineConductor')
    
    def test_gymea_app_style_example(self):
        """Test Gymea app-style log line."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Gymea0: <D> [] GymeaThrift: getPrintheadValuesAsync()"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'gymea')
        self.assertGreaterEqual(result['confidence'], 0.8)
        self.assertIn('GymeaThrift', result['payload'])
        # Query text should contain component
        self.assertIn('gymeathrift', result['query_text'])
        self.assertEqual(result['severity'], 'D')
        self.assertEqual(result['tag'], None)  # Empty tag
        self.assertEqual(result['component'], 'GymeaThrift')
    
    def test_gymea_pipe_event_example(self):
        """Test Gymea pipe-delimited event line."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Gymea0: 21.3.6|unknown-PH1|event|some message"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'gymea')
        self.assertGreaterEqual(result['confidence'], 0.8)
        # Pipe-delimited lines may not have component, but should still parse
        self.assertIsNotNone(result['payload'])
        self.assertIsNotNone(result['query_text'])
    
    def test_gymea_with_tag(self):
        """Test Gymea line with non-numeric tag."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Gymea0: <I> [InkTankController] GymeaThrift: some message"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'gymea')
        self.assertGreaterEqual(result['confidence'], 0.8)
        self.assertEqual(result['severity'], 'I')
        self.assertEqual(result['tag'], 'InkTankController')
        self.assertEqual(result['component'], 'GymeaThrift')
    
    def test_unknown_route(self):
        """Test log without route prefix."""
        log = "Some random log message without route"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'unknown')
        self.assertEqual(result['confidence'], 0.0)
        self.assertEqual(result['payload'], log)
        # Should still produce query_text
        self.assertIsNotNone(result['query_text'])
    
    def test_query_text_normalization(self):
        """Test query text normalization rules."""
        log = "2026-01-06T09:47:26.310054+11:00 RS20300529 Kareela0: <E> [#4] MMCap: localhost:9210:Dyn-ultron:LIFTER not at cap, instead at home."
        result = parse_log_line(log)
        
        query = result['query_text']
        # Should not contain timestamp/host
        self.assertNotIn('2026-01-06', query)
        self.assertNotIn('rs20300529', query)
        # Should not contain port
        self.assertNotIn('9210', query)
        # Should not contain localhost
        self.assertNotIn('localhost', query)
        # Should contain normalized message
        self.assertIn('mmcap', query)
        self.assertIn('lifter', query)
        self.assertIn('not at cap', query)
        self.assertIn('instead at home', query)
    
    def test_never_fails(self):
        """Test that parser never raises exceptions."""
        test_cases = [
            None,
            "",
            "   ",
            "Invalid log",
            123,  # Wrong type
        ]
        
        for case in test_cases:
            try:
                result = parse_log_line(case)
                self.assertIsInstance(result, dict)
                self.assertIn('route', result)
                self.assertIn('confidence', result)
                self.assertIn('payload', result)
                self.assertIn('query_text', result)
            except Exception as e:
                self.fail(f"Parser failed on {case}: {e}")
    
    def test_kareela_with_different_number(self):
        """Test Kareela route with different number (not just 0)."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela1: <E> [#4] Test: message"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'kareela')
        self.assertGreaterEqual(result['confidence'], 0.8)
    
    def test_gymea_with_different_number(self):
        """Test Gymea route with different number."""
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Gymea2: <I> [#4] Test: message"
        result = parse_log_line(log)
        
        self.assertEqual(result['route'], 'gymea')
        self.assertGreaterEqual(result['confidence'], 0.8)
    
    def test_transport_prefix_stripping(self):
        """Test that transport prefixes are stripped from message portion."""
        log = "2026-01-06T09:47:26.310054+11:00 RS20300529 Kareela0: <E> [#4] MMCap: localhost:9210:Dyn-ultron:LIFTER not at cap"
        result = parse_log_line(log)
        
        query = result['query_text']
        # Should contain component and message, but not transport prefix
        self.assertIn('mmcap', query)
        self.assertIn('lifter', query)
        self.assertIn('not at cap', query)
        # Should NOT contain transport prefix parts
        self.assertNotIn('localhost', query)
        self.assertNotIn('9210', query)
        self.assertNotIn('dyn-ultron', query)


if __name__ == '__main__':
    unittest.main()

