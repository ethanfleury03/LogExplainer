#!/usr/bin/env python2
"""
Test harness for extraction system.

Tests decorator extraction, signature formatting, boundary detection,
and nested function handling.

Usage:
    python tools/test_extraction.py
"""

from __future__ import print_function

import os
import sys
import tempfile
import shutil

# Add parent directory to path to import ingest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ingest import extract_function_chunk, _build_function_boundary_map
import ast


# Test cases as strings
TEST_CASES = [
    {
        'name': 'simple_function',
        'code': '''def simple_func(x, y):
    """Simple docstring."""
    return x + y
''',
        'expected_def_line': 1,
        'expected_decorators': [],
        'has_signature_original': True,
    },
    {
        'name': 'function_with_decorator',
        'code': '''@property
def get_value(self):
    """Get the value."""
    return self._value
''',
        'expected_def_line': 2,
        'expected_decorators': ['@property'],
        'has_signature_original': True,
    },
    {
        'name': 'function_with_multiline_decorator',
        'code': '''@decorator(
    arg1=1,
    arg2=2
)
def decorated_func():
    pass
''',
        'expected_def_line': 5,
        'expected_decorators': ['@decorator(', '    arg1=1,', '    arg2=2', ')'],
        'has_signature_original': True,
    },
    {
        'name': 'function_with_leading_comment',
        'code': '''# This is a comment
# Another comment line
def commented_func():
    """Function with leading comments."""
    pass
''',
        'expected_def_line': 3,
        'expected_decorators': [],
        'has_leading_comment': True,
    },
    {
        'name': 'function_with_multiline_signature',
        'code': '''def multiline_sig(
    arg1,
    arg2,
    arg3
):
    """Function with multi-line signature."""
    return arg1 + arg2 + arg3
''',
        'expected_def_line': 1,
        'expected_decorators': [],
        'has_multiline_signature': True,
    },
    {
        'name': 'nested_function',
        'code': '''def outer_func():
    """Outer function."""
    x = 1
    
    def inner_func():
        """Inner function."""
        return x
    
    return inner_func()
''',
        'expected_def_line': 1,
        'expected_nested': True,
    },
    {
        'name': 'class_method',
        'code': '''class MyClass:
    @classmethod
    def class_method(cls):
        """Class method."""
        return cls
''',
        'expected_def_line': 3,
        'expected_decorators': ['@classmethod'],
        'expected_class': 'MyClass',
    },
    {
        'name': 'function_with_tabs',
        'code': '''def tabbed_func():
\t"""Function with tab indentation."""
\treturn 42
''',
        'expected_def_line': 1,
        'expected_decorators': [],
    },
]


def run_test_case(test_case):
    """Run a single test case and return (passed, message)."""
    name = test_case['name']
    code = test_case['code']
    
    try:
        # Parse AST
        tree = ast.parse(code)
        
        # Find function node
        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_node = node
                break
        
        if func_node is None:
            return (False, "No function found in test case")
        
        # Build boundary map
        source_lines = code.splitlines()
        boundary_map = _build_function_boundary_map(source_lines, code)
        
        # Extract chunk
        chunk = extract_function_chunk(
            'test_file.py', func_node, source_lines,
            class_name=test_case.get('expected_class'),
            boundary_map=boundary_map,
            source_text=code
        )
        
        # Verify def_line
        if chunk['def_line'] != test_case['expected_def_line']:
            return (False, "def_line mismatch: expected {}, got {}".format(
                test_case['expected_def_line'], chunk['def_line']))
        
        # Verify decorators
        expected_decorators = test_case.get('expected_decorators', [])
        if len(chunk['decorators']) != len(expected_decorators):
            return (False, "decorator count mismatch: expected {}, got {} ({})".format(
                len(expected_decorators), len(chunk['decorators']), chunk['decorators']))
        
        for i, expected_decor in enumerate(expected_decorators):
            if i < len(chunk['decorators']):
                actual = chunk['decorators'][i].strip()
                if expected_decor.strip() not in actual and actual not in expected_decor.strip():
                    return (False, "decorator {} mismatch: expected '{}', got '{}'".format(
                        i, expected_decor, actual))
        
        # Verify signature_original exists and preserves formatting
        if test_case.get('has_signature_original', False):
            if not chunk.get('signature_original'):
                return (False, "signature_original missing")
            if '\n' in chunk['signature_original'] and test_case.get('has_multiline_signature'):
                # Multi-line signature should preserve newlines
                if chunk['signature_original'].count('\n') < 1:
                    return (False, "signature_original should preserve newlines for multi-line sig")
        
        # Verify leading comment
        if test_case.get('has_leading_comment', False):
            if not chunk.get('leading_comment'):
                return (False, "leading_comment missing")
        
        # Verify end_line_inclusive is valid
        if chunk['end_line_inclusive'] < chunk['def_line']:
            return (False, "end_line_inclusive ({}) < def_line ({})".format(
                chunk['end_line_inclusive'], chunk['def_line']))
        
        # Verify nested function doesn't break parent
        if test_case.get('expected_nested', False):
            # Should have both outer and inner functions extracted
            # (This is tested at a higher level, but we can verify structure)
            if chunk['end_line_inclusive'] <= chunk['def_line']:
                return (False, "end_line_inclusive too small for nested function")
        
        # Verify backward compatibility fields exist
        required_fields = ['file_path', 'function_name', 'line_start', 'line_end',
                          'signature', 'code', 'chunk_id']
        for field in required_fields:
            if field not in chunk:
                return (False, "Missing backward-compatible field: {}".format(field))
        
        return (True, "PASS")
    
    except Exception as e:
        import traceback
        return (False, "Exception: {}\n{}".format(e, traceback.format_exc()))


def main():
    """Run all test cases."""
    print("=" * 80)
    print("Extraction System Test Harness")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    
    for test_case in TEST_CASES:
        name = test_case['name']
        print("Test: {} ... ".format(name), end='')
        sys.stdout.flush()
        
        passed_test, message = run_test_case(test_case)
        
        if passed_test:
            print("PASS")
            passed += 1
        else:
            print("FAIL")
            print("  {}".format(message))
            failed += 1
    
    print()
    print("=" * 80)
    print("Results: {} passed, {} failed".format(passed, failed))
    print("=" * 80)
    
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()

