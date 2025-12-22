# Integration Prompt: Migrating from Live Filesystem Scan to Chunk-Based Indexing

## Context

I have an existing Arrow Log Helper system that helps technicians analyze printer logs by searching codebases for error messages. The system currently uses **live filesystem scanning** but I've built a new **chunk-based indexing system** that is much faster. I need to integrate the new system while maintaining backward compatibility and adding machine identification.

## What Was Built (New Chunk-Based System)

### 1. Indexing Script (`tools/ingest.py`)

**Purpose**: Pre-indexes a codebase by extracting all functions and their error messages into a searchable JSON structure.

**Key Features**:
- Python 2.7.5 compatible, stdlib only
- Extracts functions with full metadata:
  - Function signature (handles multi-line signatures)
  - Leading comment/docstring blocks above functions (may contain signature info)
  - Function docstring
  - Complete function code
  - Error messages extracted from logging calls, exceptions, print statements
  - Log levels (E/W/I), source types (logging/exception/print)
- Two-level index structure:
  - `chunks`: Array of all function chunks with full metadata
  - `error_index`: Dictionary mapping error message (lowercase) → list of chunk references
- Deterministic chunk IDs (SHA256 hash of chunk content)
- Statistics: files processed, functions found, errors found, elapsed time

**Usage**:
```bash
python tools/ingest.py --root /opt/memjet --out /index.json --progress
```

**Output Format** (JSON):
```json
{
  "chunks": [
    {
      "chunk_id": "abc123...",
      "file_path": "/opt/memjet/path/to/file.py",
      "function_name": "handle_connection",
      "class_name": "ConnectionManager",
      "line_start": 45,
      "line_end": 78,
      "signature": "def handle_connection(self, host, port, timeout=30):",
      "code": "def handle_connection(...):\n    ...",
      "docstring": "Handles network connections...",
      "leading_comment": "# Signature: handle_connection(host, port, timeout)\n...",
      "error_messages": [
        {
          "message": "Connection failed",
          "log_level": "E",
          "source_type": "logging"
        }
      ],
      "log_levels": ["E", "W"]
    }
  ],
  "error_index": {
    "connection failed": [
      {
        "chunk_id": "abc123...",
        "original_message": "Connection failed",
        "log_level": "E",
        "source_type": "logging"
      }
    ]
  },
  "stats": {
    "files_processed": 101,
    "functions_found": 809,
    "errors_found": 533,
    "elapsed_seconds": 0.44
  },
  "total_chunks": 809,
  "total_errors": 533
}
```

### 2. Supporting Scripts

- `tools/repo_fingerprint.py`: Generates deterministic manifests for comparing codebases across machines
- `tools/benchmark_index_time.py`: Benchmarks indexing time for codebases
- `tools/inspect_index.py`: Inspects index files for debugging

## Current System Architecture (Live Filesystem Scan)

### Current Workflow

1. **Entry Point**: `RUN_ME.py` → launches GUI via `arrow_log_helper.__main__`
2. **GUI**: `src/arrow_log_helper/gui.py` - Tkinter-based interface
3. **Analysis**: `src/arrow_log_helper/analyzer.py` → calls `search_code.search_message_exact_in_roots()`
4. **Search**: `src/arrow_log_helper/search_code.py`:
   - Walks filesystem every search
   - Searches line-by-line for error message
   - Returns matches with file path, line number, line text
5. **Enrichment**: `src/arrow_log_helper/extract_enclosure.py`:
   - Extracts function/class context around matches
   - Gets signatures, docstrings, leading comments
6. **UI Bundle**: `src/arrow_log_helper/ui_bundle.py`:
   - Formats results for GUI display
   - Computes confidence percentages, location strings

### Current Data Flow

```
User pastes log → GUI → analyzer.analyze() → search_code.search_message_exact_in_roots()
  → (scans all files) → extract_enclosure.extract_enclosure() → ui_bundle.build_ui_bundle()
  → GUI displays results
```

### Current Settings/Configuration

- Scan roots: `/opt/memjet` (configurable via env var `ARROW_LOG_HELPER_ROOTS`)
- Data directory: `/arrow-log-helper-data` (writable, for exports)
- Settings stored in `self._settings` dict in GUI
- No machine identification currently

## Integration Requirements

### 1. Machine Identification

**Requirement**: Each printer machine needs a unique identifier for its index file.

**Options**:
- Machine serial number (from log parsing: `RS20300529` format)
- Hostname
- Custom machine ID file
- Combination: `{serial}_{hostname}`

**Index File Naming**:
- Format: `/arrow-log-helper-data/index_{machine_id}.json`
- Example: `/arrow-log-helper-data/index_RS20300529.json`
- Fallback: `/arrow-log-helper-data/index_default.json` if no ID available

**Machine ID Detection**:
- Try to extract from log line (if available): `RS20300529` pattern
- Try hostname: `os.uname()[1]` or `socket.gethostname()`
- Try custom file: `/opt/memjet/.machine_id` or `/arrow-log-helper-data/.machine_id`
- Fallback to "default"

### 2. Index Management

**Index Loading**:
- On GUI startup: detect machine ID → load corresponding index
- If index missing: show warning, offer to index or use live scan fallback
- Index location: `{data_dir}/index_{machine_id}.json`

**Index Creation/Update**:
- Add "Index Codebase" button/menu option in GUI
- Run `ingest.py` logic (or import as module)
- Show progress during indexing
- Save to `{data_dir}/index_{machine_id}.json`
- Update status: "Index ready" or "Index missing - using live scan"

**Index Validation**:
- Check if index exists and is valid JSON
- Check if index is stale (optional: compare with codebase fingerprint)
- Warn if index is older than codebase files

### 3. Search Integration

**New Search Function**: Create `search_chunk_index()` in `search_code.py` or new module

**Functionality**:
```python
def search_chunk_index(error_message, index_path, case_insensitive=False):
    """
    Search chunk-based index for error message.
    
    Returns list of matches in format compatible with existing system:
    [
      {
        "path": "/opt/memjet/path/to/file.py",
        "line_no": 45,
        "line_text": "logger.error('Connection failed')",
        "match_type": "exact_message",
        "score": 1.0,
        "chunk_id": "abc123...",
        # ... existing fields for compatibility
      }
    ]
    """
```

**Search Strategy**:
1. Normalize error message (lowercase, strip)
2. Look up in `error_index` dictionary
3. Get chunk IDs from matches
4. Load full chunk metadata from `chunks` array
5. Convert to existing match format for UI compatibility
6. Return matches sorted by relevance

**Fallback to Live Scan**:
- If index missing/invalid → use existing `search_message_exact_in_roots()`
- Show status: "Using index" vs "Using live scan"

### 4. UI Changes

**GUI Updates Needed**:

1. **Machine ID Display**:
   - Show current machine ID in status bar or header
   - Format: "Machine: RS20300529" or "Machine: default"

2. **Index Status**:
   - Show index status: "Index ready" (green) or "Index missing" (yellow)
   - Show index stats: "809 functions, 533 errors indexed"
   - Show index age: "Indexed 2 hours ago"

3. **Index Management UI**:
   - "Index Codebase" button (in menu or toolbar)
   - Progress dialog during indexing
   - "Re-index" option if index exists
   - "Select Machine" option to switch between multiple indexes

4. **Search Method Indicator**:
   - Show which method is being used: "Searching index..." or "Scanning filesystem..."
   - Show search speed: "Found 5 matches in 0.02s" (index) vs "Found 5 matches in 1.2s" (live scan)

5. **Settings Panel**:
   - Add index-related settings:
     - Auto-index on startup (if missing)
     - Index refresh interval
     - Preferred search method (index vs live scan)

### 5. Analyzer Integration

**Modify `analyzer.py`**:

```python
def analyze(text, settings=None, progress_cb=None, defaults_module=None):
    """
    Updated to use chunk index if available, fallback to live scan.
    """
    # ... existing log parsing ...
    
    # Check for index
    machine_id = _detect_machine_id(parsed_all)
    index_path = _get_index_path(machine_id, settings)
    
    if index_path and os.path.exists(index_path):
        # Use chunk index
        matches, scan_stats = search_chunk_index(
            message, index_path, 
            case_insensitive=s.get("case_insensitive", False)
        )
        scan_stats["search_method"] = "chunk_index"
    else:
        # Fallback to live scan
        matches, scan_stats = search_code.search_message_exact_in_roots(...)
        scan_stats["search_method"] = "live_scan"
    
    # ... rest of existing enrichment logic ...
```

### 6. Backward Compatibility

**Requirements**:
- System must work without index (fallback to live scan)
- Existing GUI/workflow should remain functional
- No breaking changes to existing APIs
- Index is optional enhancement, not required

**Migration Path**:
1. Deploy new code with index support (backward compatible)
2. Index can be created on-demand or pre-deployed
3. System automatically uses index if available
4. Gradually migrate all machines to indexed mode

## Implementation Tasks

### Phase 1: Core Index Search
- [ ] Create `search_chunk_index()` function
- [ ] Add machine ID detection logic
- [ ] Integrate into `analyzer.py` with fallback
- [ ] Test search results match existing format

### Phase 2: Index Management
- [ ] Add index creation function (import/call `ingest.py` logic)
- [ ] Add index validation/loading
- [ ] Add index path resolution
- [ ] Handle missing/invalid indexes gracefully

### Phase 3: UI Integration
- [ ] Add machine ID display
- [ ] Add index status indicator
- [ ] Add "Index Codebase" button/menu
- [ ] Add progress dialog for indexing
- [ ] Update search status messages
- [ ] Add index management settings

### Phase 4: Testing & Polish
- [ ] Test with and without index
- [ ] Test machine ID detection
- [ ] Test index creation from GUI
- [ ] Test fallback to live scan
- [ ] Performance comparison (index vs live scan)
- [ ] Error handling for corrupted indexes

## File Structure Changes

### New Files
- `src/arrow_log_helper/chunk_search.py` - Chunk index search functions
- `src/arrow_log_helper/machine_id.py` - Machine ID detection
- `src/arrow_log_helper/index_manager.py` - Index creation/management

### Modified Files
- `src/arrow_log_helper/analyzer.py` - Add index search integration
- `src/arrow_log_helper/gui.py` - Add index UI elements
- `src/arrow_log_helper/config_defaults.py` - Add index-related defaults

### Existing Files (No Changes)
- `tools/ingest.py` - Keep as standalone script, also importable
- `src/arrow_log_helper/search_code.py` - Keep for fallback
- `src/arrow_log_helper/extract_enclosure.py` - Keep for compatibility
- `RUN_ME.py` - No changes needed

## Key Design Decisions

1. **Index Format**: JSON (readable, no dependencies, Python 2.7 compatible)
2. **Search Compatibility**: Convert chunk results to existing match format
3. **Fallback Strategy**: Always fallback to live scan if index unavailable
4. **Machine ID**: Extract from logs first, then hostname, then default
5. **Index Location**: In writable data directory, not in codebase
6. **Index Naming**: `index_{machine_id}.json` for multiple machines support

## Success Criteria

- [ ] Tech can paste error message and get instant results (if indexed)
- [ ] System works without index (fallback to live scan)
- [ ] Machine ID is automatically detected
- [ ] Index can be created from GUI
- [ ] Multiple machines can have separate indexes
- [ ] Performance: Index search < 0.1s, Live scan ~1-2s
- [ ] No breaking changes to existing functionality

## Questions to Resolve

1. Should index be created automatically on first use, or manually?
2. How to handle codebase updates? Auto-reindex or manual trigger?
3. Should we support multiple indexes per machine (different codebase versions)?
4. Index size limits? (current: ~2MB for 800 functions seems fine)
5. Should index include file hashes for staleness detection?

## Notes

- All code must remain Python 2.7.5 compatible
- Standard library only (no external dependencies)
- Read-only for codebase (index is in writable data dir)
- Maintain existing safety guarantees (write firewall, etc.)

