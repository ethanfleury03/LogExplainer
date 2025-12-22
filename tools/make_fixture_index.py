#!/usr/bin/env python
"""
Generate a fixture index JSON for testing Error Debug feature.

Creates a small valid index with 10-20 chunks and error messages.
"""

import json
import time
import hashlib
from datetime import datetime

def make_fixture_index():
    """Generate a fixture index for testing."""
    
    # Sample chunks with various error messages
    chunks = [
        {
            "chunk_id": "chunk_001",
            "file_path": "src/utils/connection.py",
            "function_name": "connect_to_printer",
            "class_name": None,
            "line_start": 10,
            "line_end": 25,
            "signature": "def connect_to_printer(host: str, port: int) -> bool:",
            "code": "def connect_to_printer(host: str, port: int) -> bool:\n    try:\n        socket.connect((host, port))\n        return True\n    except Exception as e:\n        logging.error('connection failed: %s', str(e))\n        return False",
            "docstring": "Connect to printer via socket.",
            "leading_comment": None,
            "error_messages": [
                {"message": "connection failed", "log_level": "ERROR", "source_type": "logging"}
            ],
            "log_levels": ["ERROR"]
        },
        {
            "chunk_id": "chunk_002",
            "file_path": "src/utils/connection.py",
            "function_name": "reconnect",
            "class_name": None,
            "line_start": 30,
            "line_end": 45,
            "signature": "def reconnect(max_retries: int = 3):",
            "code": "def reconnect(max_retries: int = 3):\n    for i in range(max_retries):\n        if connect_to_printer('localhost', 9100):\n            return True\n        logging.warning('reconnection attempt %d failed', i + 1)\n    raise ConnectionError('unable to establish connection')",
            "docstring": None,
            "leading_comment": None,
            "error_messages": [
                {"message": "reconnection attempt failed", "log_level": "WARNING", "source_type": "logging"},
                {"message": "unable to establish connection", "log_level": None, "source_type": "exception"}
            ],
            "log_levels": ["WARNING"]
        },
        {
            "chunk_id": "chunk_003",
            "file_path": "src/printer/status.py",
            "function_name": "check_status",
            "class_name": "PrinterStatus",
            "line_start": 50,
            "line_end": 70,
            "signature": "def check_status(self) -> dict:",
            "code": "def check_status(self) -> dict:\n    if not self.is_connected:\n        logging.error('printer not connected')\n        return {'status': 'offline'}\n    try:\n        response = self.send_command('STATUS')\n        return response\n    except TimeoutError:\n        logging.error('status check timeout')\n        return {'status': 'timeout'}",
            "docstring": "Check printer status.",
            "leading_comment": None,
            "error_messages": [
                {"message": "printer not connected", "log_level": "ERROR", "source_type": "logging"},
                {"message": "status check timeout", "log_level": "ERROR", "source_type": "logging"}
            ],
            "log_levels": ["ERROR"]
        },
        {
            "chunk_id": "chunk_004",
            "file_path": "src/printer/print_job.py",
            "function_name": "start_print",
            "class_name": "PrintJob",
            "line_start": 100,
            "line_end": 120,
            "signature": "def start_print(self, file_path: str) -> bool:",
            "code": "def start_print(self, file_path: str) -> bool:\n    if not os.path.exists(file_path):\n        raise FileNotFoundError('print file not found')\n    if self.is_busy:\n        logging.warning('printer busy, queueing job')\n        return False\n    logging.info('starting print job')\n    return True",
            "docstring": "Start a print job.",
            "leading_comment": None,
            "error_messages": [
                {"message": "print file not found", "log_level": None, "source_type": "exception"},
                {"message": "printer busy, queueing job", "log_level": "WARNING", "source_type": "logging"}
            ],
            "log_levels": ["WARNING", "INFO"]
        },
        {
            "chunk_id": "chunk_005",
            "file_path": "src/utils/config.py",
            "function_name": "load_config",
            "class_name": None,
            "line_start": 15,
            "line_end": 35,
            "signature": "def load_config(config_path: str) -> dict:",
            "code": "def load_config(config_path: str) -> dict:\n    try:\n        with open(config_path, 'r') as f:\n            return json.load(f)\n    except FileNotFoundError:\n        logging.error('config file not found: %s', config_path)\n        return {}\n    except json.JSONDecodeError as e:\n        logging.error('invalid config file: %s', str(e))\n        return {}",
            "docstring": "Load configuration from file.",
            "leading_comment": None,
            "error_messages": [
                {"message": "config file not found", "log_level": "ERROR", "source_type": "logging"},
                {"message": "invalid config file", "log_level": "ERROR", "source_type": "logging"}
            ],
            "log_levels": ["ERROR"]
        }
    ]
    
    # Build error_index mapping error messages to chunks
    error_index = {}
    for chunk in chunks:
        for err in chunk.get('error_messages', []):
            msg = err['message']
            normalized = msg.lower().strip()
            if normalized not in error_index:
                error_index[normalized] = []
            error_index[normalized].append({
                'chunk_id': chunk['chunk_id'],
                'original_message': msg
            })
    
    # Stats
    stats = {
        'files_processed': 5,
        'files_failed': 0,
        'functions_found': 5,
        'errors_found': len(error_index),
        'start_time': time.time() - 0.5,
        'elapsed_seconds': 0.5
    }
    
    # Build index
    index = {
        "schema_version": "1.0",
        "created_at": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        "chunks": chunks,
        "error_index": error_index,
        "stats": stats,
        "total_chunks": len(chunks),
        "total_errors": len(error_index)
    }
    
    return index


if __name__ == '__main__':
    import sys
    import os
    
    output_path = sys.argv[1] if len(sys.argv) > 1 else 'dev_storage/fixtures/index_fixture.json'
    
    # Create output directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Generate and save
    index = make_fixture_index()
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    
    print(f"Fixture index created: {output_path}")
    print(f"  Chunks: {index['total_chunks']}")
    print(f"  Errors: {index['total_errors']}")
    print(f"  Schema version: {index['schema_version']}")

