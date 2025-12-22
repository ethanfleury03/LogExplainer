#!/usr/bin/env python2
"""
Deterministic manifest generator and comparator for directory trees.

This utility generates a deterministic "fingerprint" (manifest) for a directory
tree and optionally compares two manifests. Designed for verifying codebase
identity across multiple machines (e.g., printer machines).

Python 2.7.5 Compatibility:
- Uses only standard library
- Compatible with Python 2.7.5 syntax and modules
- Handles unicode/str safely for Python 2.7

READ-ONLY OPERATION:
- This script ONLY READS files from the scanned directory.
- It NEVER modifies, creates, or deletes files under the scanned root.
- Output manifests are written to user-specified paths (typically root-level for easy cleanup).

Usage Examples:

Generate manifest:
    python tools/repo_fingerprint.py generate --root /opt/memjet --machine PRINTER_A --out /memjet_PRINTER_A.manifest.jsonl

Compare two manifests:
    python tools/repo_fingerprint.py compare --a /memjet_A.manifest.jsonl --b /memjet_B.manifest.jsonl --out /compare_report.txt

On two printers:
    # On PRINTER_A:
    python tools/repo_fingerprint.py generate --root /opt/memjet --machine PRINTER_A --out /memjet_PRINTER_A.manifest.jsonl
    
    # On PRINTER_B:
    python tools/repo_fingerprint.py generate --root /opt/memjet --machine PRINTER_B --out /memjet_PRINTER_B.manifest.jsonl
    
    # Compare (on either machine):
    python tools/repo_fingerprint.py compare --a /memjet_PRINTER_A.manifest.jsonl --b /memjet_PRINTER_B.manifest.jsonl --out /compare_report.txt
"""

from __future__ import print_function

import argparse
import hashlib
import json
import os
import sys
import time

# Tool version
TOOL_VERSION = "1.0.0"

# Chunk size for hashing large files (1MB)
HASH_CHUNK_SIZE = 1024 * 1024


def normalize_path(path):
    """Normalize path to use forward slashes (posix style)."""
    return path.replace(os.sep, '/')


def compute_file_hash(filepath):
    """
    Compute SHA256 hash of a file using chunked reads.
    Returns (hash_hex, error) tuple. error is None if successful.
    """
    try:
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest(), None
    except (IOError, OSError) as e:
        return None, str(e)


def get_file_info(root, filepath):
    """
    Get file information: type, size, hash, symlink target.
    Returns dict with entry data or None if unreadable.
    """
    full_path = os.path.join(root, filepath)
    rel_path = normalize_path(filepath)
    
    try:
        stat_info = os.lstat(full_path)  # lstat doesn't follow symlinks
        is_symlink = os.path.islink(full_path)
        is_dir = os.path.isdir(full_path) if not is_symlink else False
        
        entry = {
            'path': rel_path,
            'type': 'dir' if is_dir else ('symlink' if is_symlink else 'file')
        }
        
        if is_symlink:
            try:
                entry['link_target'] = normalize_path(os.readlink(full_path))
            except (OSError, IOError) as e:
                entry['link_target'] = None
                entry['error'] = 'readlink_failed: ' + str(e)
        elif is_dir:
            # Directories: just record type and path
            pass
        else:
            # Regular file: get size and hash
            entry['size'] = stat_info.st_size
            hash_hex, error = compute_file_hash(full_path)
            if error:
                entry['error'] = 'hash_failed: ' + error
                entry['size'] = stat_info.st_size  # Still record size if available
            else:
                entry['sha256'] = hash_hex
        
        return entry
    except (OSError, IOError) as e:
        # Unreadable file - include with error
        return {
            'path': rel_path,
            'type': 'file',  # Best guess
            'error': 'stat_failed: ' + str(e)
        }


def canonical_entry_line(entry):
    """
    Generate canonical string representation of an entry for fingerprinting.
    This should NOT include timestamp or machine-specific info.
    Returns a deterministic string.
    """
    # Sort keys for deterministic output
    keys = sorted(entry.keys())
    parts = []
    for key in keys:
        value = entry.get(key, '')
        # Convert value to string for consistent representation
        if value is None:
            value = ''
        parts.append('{}:{}'.format(key, value))
    return '|'.join(parts)


def generate_manifest(root, machine, out_path):
    """
    Generate manifest for directory tree.
    Returns (fingerprint_id, stats_dict) on success, (None, None) on error.
    """
    if not os.path.isdir(root):
        print("ERROR: Root path is not a directory: {}".format(root), file=sys.stderr)
        return None, None
    
    entries = []
    total_bytes = 0
    file_count = 0
    symlink_count = 0
    dir_count = 0
    error_count = 0
    
    # Walk directory tree (don't follow symlinks)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Normalize dirpath relative to root
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == '.':
            rel_dir = ''
        
        # Process directory itself (if not root)
        if rel_dir:
            dir_entry = get_file_info(root, rel_dir)
            if dir_entry:
                entries.append(dir_entry)
                if dir_entry.get('type') == 'dir':
                    dir_count += 1
        
        # Process files
        for filename in sorted(filenames):  # Sort for deterministic order
            rel_path = os.path.join(rel_dir, filename) if rel_dir else filename
            entry = get_file_info(root, rel_path)
            if entry:
                entries.append(entry)
                if entry.get('type') == 'file':
                    file_count += 1
                    total_bytes += entry.get('size', 0)
                    if 'error' in entry:
                        error_count += 1
                elif entry.get('type') == 'symlink':
                    symlink_count += 1
                    if 'error' in entry:
                        error_count += 1
                elif entry.get('type') == 'dir':
                    dir_count += 1
        
        # Sort dirnames for deterministic traversal
        dirnames.sort()
    
    # Sort entries by path for deterministic output
    entries.sort(key=lambda e: e['path'])
    
    # Compute fingerprint_id: SHA256 of concatenated canonical entry lines
    canonical_lines = []
    for entry in entries:
        canonical_lines.append(canonical_entry_line(entry))
    fingerprint_content = '\n'.join(canonical_lines)
    fingerprint_id = hashlib.sha256(fingerprint_content).hexdigest()
    
    # Prepare stats
    stats = {
        'file_count': file_count,
        'symlink_count': symlink_count,
        'dir_count': dir_count,
        'total_bytes': total_bytes,
        'error_count': error_count,
        'total_entries': len(entries)
    }
    
    # Write manifest
    try:
        with open(out_path, 'w') as f:
            # Write header as comment lines
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            f.write("# Tool version: {}\n".format(TOOL_VERSION))
            f.write("# Machine: {}\n".format(machine))
            f.write("# Root: {}\n".format(root))
            f.write("# Timestamp: {}\n".format(timestamp))
            f.write("# Total files: {}\n".format(file_count))
            f.write("# Total bytes: {}\n".format(total_bytes))
            f.write("# Total symlinks: {}\n".format(symlink_count))
            f.write("# Total directories: {}\n".format(dir_count))
            f.write("# Total entries: {}\n".format(len(entries)))
            f.write("# Errors: {}\n".format(error_count))
            f.write("# Fingerprint ID: {}\n".format(fingerprint_id))
            f.write("# ---\n")
            
            # Write entries as JSON lines
            for entry in entries:
                json_line = json.dumps(entry, sort_keys=True, ensure_ascii=False)
                f.write(json_line + '\n')
        
        return fingerprint_id, stats
    except (IOError, OSError) as e:
        print("ERROR: Failed to write manifest: {}".format(e), file=sys.stderr)
        return None, None


def parse_manifest(manifest_path):
    """
    Parse manifest file, skipping header lines.
    Returns dict mapping path -> entry, or None on error.
    """
    entries = {}
    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                line = line.rstrip('\n\r')
                # Skip header lines (comments)
                if line.startswith('#'):
                    continue
                # Skip empty lines
                if not line.strip():
                    continue
                # Parse JSON line
                try:
                    entry = json.loads(line)
                    path = entry.get('path')
                    if path:
                        entries[path] = entry
                except ValueError as e:
                    print("WARNING: Failed to parse line in {}: {}".format(manifest_path, e), file=sys.stderr)
                    continue
        return entries
    except (IOError, OSError) as e:
        print("ERROR: Failed to read manifest: {}".format(e), file=sys.stderr)
        return None


def compare_entries(entry_a, entry_b):
    """
    Compare two entries. Returns list of differences (empty if identical).
    """
    differences = []
    
    # Check type
    if entry_a.get('type') != entry_b.get('type'):
        differences.append("type: {} vs {}".format(entry_a.get('type'), entry_b.get('type')))
    
    # For files: check size and sha256
    if entry_a.get('type') == 'file' and entry_b.get('type') == 'file':
        if entry_a.get('size') != entry_b.get('size'):
            differences.append("size: {} vs {}".format(entry_a.get('size'), entry_b.get('size')))
        if entry_a.get('sha256') != entry_b.get('sha256'):
            differences.append("sha256: {} vs {}".format(
                entry_a.get('sha256', 'missing'), entry_b.get('sha256', 'missing')))
    
    # For symlinks: check link_target
    if entry_a.get('type') == 'symlink' and entry_b.get('type') == 'symlink':
        if entry_a.get('link_target') != entry_b.get('link_target'):
            differences.append("link_target: {} vs {}".format(
                entry_a.get('link_target'), entry_b.get('link_target')))
    
    # Check errors
    error_a = entry_a.get('error')
    error_b = entry_b.get('error')
    if error_a != error_b:
        if error_a and not error_b:
            differences.append("error in A: {}".format(error_a))
        elif error_b and not error_a:
            differences.append("error in B: {}".format(error_b))
        elif error_a != error_b:
            differences.append("error: {} vs {}".format(error_a, error_b))
    
    return differences


def compare_manifests(manifest_a_path, manifest_b_path, out_path=None, max_mismatches=50):
    """
    Compare two manifests.
    Returns (is_identical, diff_summary_dict).
    """
    entries_a = parse_manifest(manifest_a_path)
    entries_b = parse_manifest(manifest_b_path)
    
    if entries_a is None or entries_b is None:
        return False, None
    
    paths_a = set(entries_a.keys())
    paths_b = set(entries_b.keys())
    
    only_in_a = sorted(paths_a - paths_b)
    only_in_b = sorted(paths_b - paths_a)
    common_paths = sorted(paths_a & paths_b)
    
    different_entries = []
    for path in common_paths:
        diff_list = compare_entries(entries_a[path], entries_b[path])
        if diff_list:
            different_entries.append((path, entries_a[path], entries_b[path], diff_list))
    
    is_identical = len(only_in_a) == 0 and len(only_in_b) == 0 and len(different_entries) == 0
    
    summary = {
        'identical': is_identical,
        'only_in_a_count': len(only_in_a),
        'only_in_b_count': len(only_in_b),
        'different_count': len(different_entries),
        'only_in_a': only_in_a,
        'only_in_b': only_in_b,
        'different_entries': different_entries
    }
    
    # Print summary to stdout
    print("Comparison Results:")
    print("  Identical: {}".format("yes" if is_identical else "no"))
    print("  Only in A: {}".format(len(only_in_a)))
    print("  Only in B: {}".format(len(only_in_b)))
    print("  Different entries: {}".format(len(different_entries)))
    
    if not is_identical:
        print("\nFirst {} mismatches:".format(min(max_mismatches, len(only_in_a) + len(only_in_b) + len(different_entries))))
        count = 0
        for path in only_in_a[:max_mismatches]:
            if count >= max_mismatches:
                break
            print("  ONLY IN A: {}".format(path))
            count += 1
        for path in only_in_b[:max_mismatches - count]:
            if count >= max_mismatches:
                break
            print("  ONLY IN B: {}".format(path))
            count += 1
        for path, entry_a, entry_b, diff_list in different_entries[:max_mismatches - count]:
            if count >= max_mismatches:
                break
            print("  DIFFERENT: {} - {}".format(path, ', '.join(diff_list)))
            count += 1
    
    # Write detailed report if out_path provided
    if out_path:
        try:
            with open(out_path, 'w') as f:
                f.write("Manifest Comparison Report\n")
                f.write("=" * 80 + "\n\n")
                f.write("Manifest A: {}\n".format(manifest_a_path))
                f.write("Manifest B: {}\n".format(manifest_b_path))
                f.write("Identical: {}\n\n".format("yes" if is_identical else "no"))
                
                f.write("Summary:\n")
                f.write("  Only in A: {}\n".format(len(only_in_a)))
                f.write("  Only in B: {}\n".format(len(only_in_b)))
                f.write("  Different entries: {}\n\n".format(len(different_entries)))
                
                if only_in_a:
                    f.write("Only in A ({} entries):\n".format(len(only_in_a)))
                    f.write("-" * 80 + "\n")
                    for path in only_in_a:
                        entry = entries_a[path]
                        f.write("  {}\n".format(path))
                        f.write("    Type: {}\n".format(entry.get('type')))
                        if entry.get('type') == 'file':
                            f.write("    Size: {}\n".format(entry.get('size')))
                            f.write("    SHA256: {}\n".format(entry.get('sha256', 'N/A')))
                        elif entry.get('type') == 'symlink':
                            f.write("    Link target: {}\n".format(entry.get('link_target', 'N/A')))
                        if 'error' in entry:
                            f.write("    Error: {}\n".format(entry['error']))
                    f.write("\n")
                
                if only_in_b:
                    f.write("Only in B ({} entries):\n".format(len(only_in_b)))
                    f.write("-" * 80 + "\n")
                    for path in only_in_b:
                        entry = entries_b[path]
                        f.write("  {}\n".format(path))
                        f.write("    Type: {}\n".format(entry.get('type')))
                        if entry.get('type') == 'file':
                            f.write("    Size: {}\n".format(entry.get('size')))
                            f.write("    SHA256: {}\n".format(entry.get('sha256', 'N/A')))
                        elif entry.get('type') == 'symlink':
                            f.write("    Link target: {}\n".format(entry.get('link_target', 'N/A')))
                        if 'error' in entry:
                            f.write("    Error: {}\n".format(entry['error']))
                    f.write("\n")
                
                if different_entries:
                    f.write("Different entries ({} entries):\n".format(len(different_entries)))
                    f.write("-" * 80 + "\n")
                    for path, entry_a, entry_b, diff_list in different_entries:
                        f.write("  {}\n".format(path))
                        f.write("    Differences: {}\n".format(', '.join(diff_list)))
                        f.write("    A: {}\n".format(json.dumps(entry_a, sort_keys=True, ensure_ascii=False)))
                        f.write("    B: {}\n".format(json.dumps(entry_b, sort_keys=True, ensure_ascii=False)))
                        f.write("\n")
        except (IOError, OSError) as e:
            print("ERROR: Failed to write comparison report: {}".format(e), file=sys.stderr)
    
    return is_identical, summary


def main():
    parser = argparse.ArgumentParser(
        description='Generate and compare deterministic manifests for directory trees',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Subcommand to run')
    
    # Generate subcommand
    gen_parser = subparsers.add_parser('generate', help='Generate manifest for directory tree')
    gen_parser.add_argument('--root', required=True, help='Root directory to scan')
    gen_parser.add_argument('--machine', required=True, help='Machine label (e.g., PRINTER_A)')
    gen_parser.add_argument('--out', required=True, help='Output manifest file path')
    
    # Compare subcommand
    cmp_parser = subparsers.add_parser('compare', help='Compare two manifests')
    cmp_parser.add_argument('--a', required=True, help='Path to first manifest file')
    cmp_parser.add_argument('--b', required=True, help='Path to second manifest file')
    cmp_parser.add_argument('--out', help='Optional output report file path')
    cmp_parser.add_argument('--max-mismatches', type=int, default=50,
                           help='Maximum number of mismatches to show (default: 50)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'generate':
        fingerprint_id, stats = generate_manifest(args.root, args.machine, args.out)
        if fingerprint_id is None:
            sys.exit(1)
        
        print("Manifest generated successfully:")
        print("  Output: {}".format(args.out))
        print("  Fingerprint ID: {}".format(fingerprint_id))
        print("  Files: {}".format(stats['file_count']))
        print("  Symlinks: {}".format(stats['symlink_count']))
        print("  Directories: {}".format(stats['dir_count']))
        print("  Total bytes: {}".format(stats['total_bytes']))
        print("  Total entries: {}".format(stats['total_entries']))
        if stats['error_count'] > 0:
            print("  Errors: {}".format(stats['error_count']))
        sys.exit(0)
    
    elif args.command == 'compare':
        is_identical, summary = compare_manifests(
            args.a, args.b, args.out, args.max_mismatches
        )
        if summary is None:
            sys.exit(1)
        
        # Exit code: 0 if identical, 2 if different, 1 for errors (handled above)
        sys.exit(0 if is_identical else 2)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

