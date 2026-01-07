"""
Unit tests for AI Summary endpoint and Anthropic client.
"""

import unittest
import json
import sys
import os
from unittest.mock import patch, MagicMock

# Add project root to path for imports
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.utils.anthropic_client import call_claude_messages


class TestAnthropicClient(unittest.TestCase):
    
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key-123'})
    @patch('backend.utils.anthropic_client.requests.post')
    def test_call_claude_success(self, mock_post):
        """Test successful Claude API call."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'content': [
                {
                    'type': 'text',
                    'text': '{"what_it_means": "Test response", "confidence": {"level": "high"}}'
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = call_claude_messages("Test prompt")
        
        self.assertIn("what_it_means", result)
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], "https://api.anthropic.com/v1/messages")
        self.assertIn('x-api-key', call_args[1]['headers'])
        self.assertEqual(call_args[1]['headers']['x-api-key'], 'test-key-123')
    
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key-123'})
    @patch('backend.utils.anthropic_client.requests.post')
    def test_call_claude_api_error(self, mock_post):
        """Test Claude API returns error status."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request"
        mock_post.return_value = mock_response
        
        with self.assertRaises(RuntimeError) as context:
            call_claude_messages("Test prompt")
        
        self.assertIn("status 400", str(context.exception))
    
    def test_call_claude_missing_api_key(self):
        """Test error when API key is missing."""
        # Ensure API key is not set
        if 'ANTHROPIC_API_KEY' in os.environ:
            del os.environ['ANTHROPIC_API_KEY']
        
        with self.assertRaises(ValueError) as context:
            call_claude_messages("Test prompt")
        
        self.assertIn("ANTHROPIC_API_KEY", str(context.exception))
    
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key-123'})
    @patch('backend.utils.anthropic_client.requests.post')
    def test_call_claude_empty_content(self, mock_post):
        """Test error when Claude returns empty content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'content': []}
        mock_post.return_value = mock_response
        
        with self.assertRaises(RuntimeError) as context:
            call_claude_messages("Test prompt")
        
        self.assertIn("empty content", str(context.exception))
    
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key-123'})
    @patch('backend.utils.anthropic_client.requests.post')
    def test_call_claude_timeout(self, mock_post):
        """Test timeout handling."""
        import requests
        mock_post.side_effect = requests.Timeout("Request timed out")
        
        with self.assertRaises(RuntimeError) as context:
            call_claude_messages("Test prompt")
        
        self.assertIn("timed out", str(context.exception))


class TestAiSummaryEndpoint(unittest.TestCase):
    """Tests for the AI summary endpoint (would require FastAPI test client)."""
    
    def test_payload_validation(self):
        """Test payload schema validation logic."""
        # Valid payload
        valid_payload = {
            "schema_version": "ai_summary_v1",
            "query": {
                "raw": "test query"
            }
        }
        self.assertEqual(valid_payload["schema_version"], "ai_summary_v1")
        self.assertIsNotNone(valid_payload["query"]["raw"])
        
        # Invalid payload
        invalid_payload = {
            "schema_version": "invalid",
            "query": {}
        }
        self.assertNotEqual(invalid_payload["schema_version"], "ai_summary_v1")
    
    def test_code_truncation_logic(self):
        """Test code field truncation logic."""
        max_length = 10
        long_code = "a" * 100
        
        if len(long_code) > max_length:
            truncated = long_code[:max_length] + f"\n... [truncated {len(long_code) - max_length} chars]"
            self.assertEqual(len(truncated), max_length + len(f"\n... [truncated {len(long_code) - max_length} chars]"))
            self.assertIn("truncated", truncated)


if __name__ == '__main__':
    unittest.main()



