#!/usr/bin/env python2
"""Quick script to inspect the index file."""
from __future__ import print_function
import json
import sys

if len(sys.argv) < 2:
    print("Usage: python tools/inspect_index.py <index.json>")
    sys.exit(1)

with open(sys.argv[1], 'rb') as f:
    idx = json.load(f)

print("Index Statistics:")
print("  Total chunks: {}".format(idx['total_chunks']))
print("  Total unique errors in index: {}".format(len(idx['error_index'])))
print()

# Find chunks with error messages
chunks_with_errors = [c for c in idx['chunks'] if c.get('error_messages')]
print("Chunks with error messages: {}".format(len(chunks_with_errors)))
print()

if chunks_with_errors:
    print("Sample chunk with errors:")
    c = chunks_with_errors[0]
    print("  Function: {}".format(c['function_name']))
    print("  File: {}".format(c['file_path']))
    print("  Error messages:")
    for e in c['error_messages'][:5]:
        msg = e.get('message', '')
        print("    - {} (level: {}, type: {})".format(
            msg[:80], e.get('log_level', 'N/A'), e.get('source_type', 'N/A')
        ))
    print()

print("Sample error index entries (first 10):")
for i, (err_key, chunks) in enumerate(list(idx['error_index'].items())[:10]):
    print("  '{}' -> {} chunks".format(err_key[:70], len(chunks)))

