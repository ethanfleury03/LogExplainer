#!/usr/bin/env python2
"""
Estimate index size for a codebase.

Runs ingest.py on a provided root and reports:
- Raw file size (bytes/MB)
- Gzipped size
- Total chunks, total errors
"""

from __future__ import print_function

import argparse
import gzip
import os
import sys
import tempfile

# Import ingest functionality
sys.path.insert(0, os.path.dirname(__file__))
from ingest import index_codebase


def format_bytes(bytes_count):
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return "{:.2f} {}".format(bytes_count, unit)
        bytes_count /= 1024.0
    return "{:.2f} TB".format(bytes_count)


def main():
    parser = argparse.ArgumentParser(
        description='Estimate index size for a codebase',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--root', default='/opt/memjet',
                       help='Root directory to index (default: /opt/memjet)')
    parser.add_argument('--include-ext', nargs='+', default=['.py'],
                       help='File extensions to include (default: .py)')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.root):
        print("ERROR: Root path is not a directory: {}".format(args.root), file=sys.stderr)
        sys.exit(1)
    
    # Create temporary output file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
        tmp_path = tmp_file.name
    
    try:
        print("Indexing codebase: {}".format(args.root))
        print("This may take a moment...")
        
        # Run indexing
        index = index_codebase(
            root_path=args.root,
            output_path=tmp_path,
            include_exts=args.include_ext,
            progress_cb=None  # No progress for estimation
        )
        
        if index is None:
            print("ERROR: Indexing failed", file=sys.stderr)
            sys.exit(1)
        
        # Get file size
        raw_size = os.path.getsize(tmp_path)
        
        # Get gzipped size
        with open(tmp_path, 'rb') as f_in:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_gz:
                with gzip.open(tmp_gz.name, 'wb') as f_out:
                    f_out.writelines(f_in)
                gzipped_size = os.path.getsize(tmp_gz.name)
                os.unlink(tmp_gz.name)
        
        # Print results
        print()
        print("=" * 80)
        print("Index Size Estimation")
        print("=" * 80)
        print("Raw file size:      {} ({:,} bytes)".format(format_bytes(raw_size), raw_size))
        print("Gzipped size:        {} ({:,} bytes)".format(format_bytes(gzipped_size), gzipped_size))
        print("Compression ratio:   {:.1f}%".format((1.0 - float(gzipped_size) / raw_size) * 100))
        print()
        print("Index Statistics:")
        stats = index.get('stats', {})
        print("  Total chunks:      {:,}".format(index.get('total_chunks', 0)))
        print("  Total errors:       {:,}".format(index.get('total_errors', 0)))
        print("  Files processed:   {:,}".format(stats.get('files_processed', 0)))
        print("  Functions found:   {:,}".format(stats.get('functions_found', 0)))
        print("=" * 80)
        
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    
    sys.exit(0)


if __name__ == '__main__':
    main()

