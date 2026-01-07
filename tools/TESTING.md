# Testing the Extraction System

## Quick Test (Local)

Run the test harness:

```bash
python tools/test_extraction.py
```

This tests:
- Simple functions
- Functions with decorators (single and multi-line)
- Functions with leading comments
- Multi-line signatures
- Nested functions
- Class methods with decorators
- Tab indentation

Expected output: All 8 tests should PASS.

## Testing on Printer (Python 2.7.5)

### Prerequisites

1. Copy `tools/ingest.py` to the printer (e.g., `/root/ingest.py`)
2. Ensure Python 2.7.5 is available
3. Verify stdlib modules: `tokenize`, `ast`, `json`, `hashlib`, `argparse`

### Basic Test

```bash
# On printer
python /root/ingest.py --root /opt/memjet --out /root/test_index.json --progress
```

This will:
- Index all Python files in `/opt/memjet`
- Create `/root/test_index.json`
- Show progress updates

### Verify Output

Check that the index file contains the new fields:

```bash
# On printer (if Python 2.7 has json.tool)
python -m json.tool /root/test_index.json | head -100

# Or use a simple Python script
python -c "
import json
with open('/root/test_index.json') as f:
    idx = json.load(f)
    chunk = idx['chunks'][0] if idx['chunks'] else {}
    print('New fields present:')
    print('  def_line:', 'def_line' in chunk)
    print('  decorators:', 'decorators' in chunk)
    print('  signature_original:', 'signature_original' in chunk)
    print('  code_full:', 'code_full' in chunk)
    print('  extraction_warnings:', 'extraction_warnings' in chunk)
"
```

### Test with Real Codebase

1. Index a small subset first:
   ```bash
   python /root/ingest.py --root /opt/memjet/some/small/module --out /root/small_index.json
   ```

2. Check extraction quality:
   - Open the JSON file
   - Verify decorators are captured
   - Verify signature_original preserves formatting
   - Verify end_line_inclusive is accurate

3. Full index:
   ```bash
   python /root/ingest.py --root /opt/memjet --out /root/index.json
   ```

## Python 2.7.5 Compatibility

The code is designed for Python 2.7.5:

✅ **Compatible features:**
- Uses `from __future__ import print_function`
- Handles `StringIO` import (Python 2: `from StringIO import StringIO`)
- Handles `unicode` type (Python 2 vs 3)
- Uses `tokenize.generate_tokens` (available in Python 2.7)
- Uses `ast.parse` (available in Python 2.7)
- No f-strings, no Python 3-only syntax

✅ **Tested modules:**
- `tokenize` - stdlib in Python 2.7
- `ast` - stdlib in Python 2.7
- `json` - stdlib in Python 2.7
- `hashlib` - stdlib in Python 2.7
- `argparse` - stdlib in Python 2.7

## Verification Checklist

After running on printer, verify:

- [ ] Index file created successfully
- [ ] `schema_version` is "1.0" (backward compatible)
- [ ] All chunks have required fields: `chunk_id`, `file_path`, `function_name`, etc.
- [ ] New fields present: `def_line`, `decorators`, `signature_original`, etc.
- [ ] Decorators are captured for `@property`, `@classmethod`, etc.
- [ ] Multi-line signatures preserved in `signature_original`
- [ ] `end_line_inclusive` is accurate (not off-by-one)
- [ ] `extraction_warnings` field exists (may be empty list)
- [ ] Search still works (uses backward-compatible fields)

## Troubleshooting

**Issue: "tokenize failed" warnings**
- Check `extraction_warnings` field in chunks
- If many chunks have `"tokenize_failed_used_old_end_algo"`, there may be encoding issues
- Fallback algorithm should still work

**Issue: Decorators not captured**
- Check if decorator is at same indent level as function
- Multi-line decorators should be captured
- If missing, check `extraction_warnings` for clues

**Issue: End line incorrect**
- Check `extraction_warnings` for `"end_line_fallback_used"`
- Tokenize-based detection should be more accurate than fallback

## Upload to Backend

Once verified on printer:

1. Upload index file via backend API:
   ```bash
   curl -X POST "http://your-backend/api/error-debug/machines/{machine_id}/versions" \
     -F "file=@/root/index.json" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

2. Verify upload succeeded (check backend logs)

3. Test search functionality to ensure backward compatibility




