#!/usr/bin/env python2
"""
Benchmark script to estimate indexing time for a codebase.

This script simulates the indexing process by scanning all files in a directory
tree and measuring the time it takes. This helps estimate how long it will take
to index each printer's codebase.

Python 2.7.5 Compatible - Standard library only.

Usage:
    python tools/benchmark_index_time.py --root /opt/memjet
    python tools/benchmark_index_time.py --root /opt/memjet --include-ext .py .c .cpp .h
"""

from __future__ import print_function

import argparse
import os
import sys
import time


def safe_walk_files(roots, include_exts=None, exclude_dir_names=None, max_file_bytes=10*1024*1024):
    """
    Walk files in roots, respecting include_exts and exclude_dir_names.
    Yields file paths.
    """
    if include_exts is None:
        include_exts = [".py"]
    
    # Normalize extensions
    include_exts = [e.lower() if e.startswith('.') else '.' + e.lower() for e in include_exts]
    
    if exclude_dir_names is None:
        exclude_dir_names = set()
    else:
        exclude_dir_names = set(exclude_dir_names)
    
    roots_list = roots if isinstance(roots, (list, tuple)) else [roots]
    
    for root in roots_list:
        if not os.path.isdir(root):
            continue
        
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Filter out excluded directories
            dirnames[:] = [d for d in dirnames if d not in exclude_dir_names]
            
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                
                # Check extension
                _, ext = os.path.splitext(filename)
                if ext.lower() not in include_exts:
                    continue
                
                # Check file size
                try:
                    stat_info = os.stat(filepath)
                    if stat_info.st_size > max_file_bytes:
                        continue
                except (OSError, IOError):
                    continue
                
                yield filepath


def benchmark_scan(root, include_exts=None, exclude_dir_names=None, max_file_bytes=10*1024*1024, sample_read=False):
    """
    Benchmark scanning a codebase.
    
    Args:
        root: Root directory to scan
        include_exts: List of file extensions to include (e.g., ['.py', '.c'])
        exclude_dir_names: Set of directory names to exclude
        max_file_bytes: Maximum file size to process
        sample_read: If True, actually read a sample of files (slower but more accurate)
    
    Returns:
        dict with statistics
    """
    stats = {
        'files_found': 0,
        'files_scanned': 0,
        'total_bytes': 0,
        'files_skipped_too_big': 0,
        'files_skipped_unreadable': 0,
        'elapsed_seconds': 0.0,
    }
    
    start_time = time.time()
    
    # Default exclude directories (common build/cache dirs)
    if exclude_dir_names is None:
        exclude_dir_names = {
            '__pycache__', '.git', '.svn', '.hg',
            'node_modules', 'dist', 'build', 'out', 'target',
            'venv', '.venv', 'env', '.env',
            '.idea', '.vscode',
        }
    
    for filepath in safe_walk_files([root], include_exts=include_exts, 
                                     exclude_dir_names=exclude_dir_names,
                                     max_file_bytes=max_file_bytes):
        stats['files_found'] += 1
        
        try:
            stat_info = os.stat(filepath)
            file_size = stat_info.st_size
            stats['total_bytes'] += file_size
            
            if sample_read:
                # Actually read the file to simulate indexing
                try:
                    with open(filepath, 'rb') as f:
                        # Read in chunks to avoid memory issues
                        chunk_size = 1024 * 1024  # 1MB chunks
                        bytes_read = 0
                        while bytes_read < file_size:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            bytes_read += len(chunk)
                    stats['files_scanned'] += 1
                except (IOError, OSError) as e:
                    stats['files_skipped_unreadable'] += 1
            else:
                # Just count files (faster, less accurate)
                stats['files_scanned'] += 1
                
        except (OSError, IOError) as e:
            stats['files_skipped_unreadable'] += 1
    
    stats['elapsed_seconds'] = time.time() - start_time
    
    return stats


def format_time(seconds):
    """Format seconds as human-readable time."""
    if seconds < 60:
        return "{:.2f} seconds".format(seconds)
    elif seconds < 3600:
        minutes = seconds / 60.0
        return "{:.2f} minutes ({:.2f} seconds)".format(minutes, seconds)
    else:
        hours = seconds / 3600.0
        minutes = (seconds % 3600) / 60.0
        return "{:.1f} hours {:.1f} minutes ({:.2f} seconds)".format(hours, minutes, seconds)


def format_bytes(bytes_count):
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return "{:.2f} {}".format(bytes_count, unit)
        bytes_count /= 1024.0
    return "{:.2f} PB".format(bytes_count)


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark indexing time for a codebase',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick scan (just count files, fast):
  python tools/benchmark_index_time.py --root /opt/memjet
  
  # Accurate scan (actually read files, slower but more accurate):
  python tools/benchmark_index_time.py --root /opt/memjet --sample-read
  
  # Scan specific file types:
  python tools/benchmark_index_time.py --root /opt/memjet --include-ext .py .c .cpp .h
  
  # Scan with custom excludes:
  python tools/benchmark_index_time.py --root /opt/memjet --exclude-dir __pycache__ .git
        """
    )
    parser.add_argument('--root', required=True, help='Root directory to scan')
    parser.add_argument('--include-ext', nargs='+', default=['.py'],
                       help='File extensions to include (default: .py)')
    parser.add_argument('--exclude-dir', nargs='+', default=None,
                       help='Directory names to exclude (default: common build/cache dirs)')
    parser.add_argument('--max-file-bytes', type=int, default=10*1024*1024,
                       help='Maximum file size to process in bytes (default: 10MB)')
    parser.add_argument('--sample-read', action='store_true',
                       help='Actually read files to simulate indexing (slower but more accurate)')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.root):
        print("ERROR: Root path is not a directory: {}".format(args.root), file=sys.stderr)
        sys.exit(1)
    
    print("Benchmarking indexing time for: {}".format(args.root))
    print("=" * 80)
    print("Configuration:")
    print("  Include extensions: {}".format(', '.join(args.include_ext)))
    if args.exclude_dir:
        print("  Exclude directories: {}".format(', '.join(args.exclude_dir)))
    print("  Max file size: {}".format(format_bytes(args.max_file_bytes)))
    print("  Sample read: {}".format("Yes (accurate)" if args.sample_read else "No (fast)"))
    print()
    print("Scanning...")
    
    start_time = time.time()
    stats = benchmark_scan(
        root=args.root,
        include_exts=args.include_ext,
        exclude_dir_names=args.exclude_dir,
        max_file_bytes=args.max_file_bytes,
        sample_read=args.sample_read
    )
    
    print()
    print("=" * 80)
    print("Results:")
    print("  Files found: {:,}".format(stats['files_found']))
    print("  Files scanned: {:,}".format(stats['files_scanned']))
    print("  Total size: {}".format(format_bytes(stats['total_bytes'])))
    if stats['files_skipped_too_big'] > 0:
        print("  Files skipped (too big): {:,}".format(stats['files_skipped_too_big']))
    if stats['files_skipped_unreadable'] > 0:
        print("  Files skipped (unreadable): {:,}".format(stats['files_skipped_unreadable']))
    print()
    print("  Elapsed time: {}".format(format_time(stats['elapsed_seconds'])))
    print()
    
    # Calculate estimates
    if stats['files_scanned'] > 0:
        avg_time_per_file = stats['elapsed_seconds'] / stats['files_scanned']
        avg_bytes_per_second = stats['total_bytes'] / stats['elapsed_seconds'] if stats['elapsed_seconds'] > 0 else 0
        
        print("Estimates:")
        print("  Average time per file: {:.3f} seconds".format(avg_time_per_file))
        print("  Processing speed: {}/second".format(format_bytes(avg_bytes_per_second)))
        print()
        
        if not args.sample_read:
            print("NOTE: This was a fast scan (file counting only).")
            print("      For more accurate timing, use --sample-read flag.")
            print("      Actual indexing may take 2-10x longer depending on file sizes.")
    
    print("=" * 80)
    
    # Exit code
    sys.exit(0)


if __name__ == '__main__':
    main()

