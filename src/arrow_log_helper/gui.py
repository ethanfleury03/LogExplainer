from __future__ import absolute_import, print_function

import json
import os
import sys

try:
    import Tkinter as tk  # Python 2
    import tkMessageBox as messagebox
    import ttk
except ImportError:  # pragma: no cover (py3 fallback)
    import tkinter as tk  # type: ignore
    from tkinter import messagebox  # type: ignore
    from tkinter import ttk  # type: ignore


try:
    # Arrow Log Helper defaults (stdlib-only, data-only).
    from arrow_log_helper.config_defaults import (  # noqa: F401
        DEFAULT_EXCLUDE_DIRS,
        DEFAULT_INCLUDE_EXT,
        DEFAULT_ROOTS,
        DEFAULT_MAX_RESULTS,
        DEFAULT_MAX_FILE_BYTES,
        DEFAULT_MAX_SECONDS,
        DEFAULT_MAX_FILES_SCANNED,
        DEFAULT_PROGRESS_EVERY_N_FILES,
    )
except Exception:
    DEFAULT_ROOTS = []
    DEFAULT_INCLUDE_EXT = [".py"]
    DEFAULT_EXCLUDE_DIRS = []
    DEFAULT_MAX_RESULTS = 10
    DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024
    DEFAULT_MAX_SECONDS = 6
    DEFAULT_MAX_FILES_SCANNED = 20000
    DEFAULT_PROGRESS_EVERY_N_FILES = 100


from arrow_log_helper import analyzer
from arrow_log_helper import write_firewall
from arrow_log_helper import repo_discover
from arrow_log_helper import config_store
from arrow_log_helper import ui_bundle


def _safe_text(text):
    if text is None:
        return ""
    try:
        # Python 2: ensure we don't crash on unicode/bytes surprises.
        if isinstance(text, unicode):  # noqa: F821  (py2 only)
            return text
    except Exception:
        pass
    try:
        return str(text)
    except Exception:
        return repr(text)


class ArrowLogHelperApp(object):
    def __init__(self, root):
        self.root = root
        self.root.title("Arrow Log Helper (POC)")

        self._data_dir = os.environ.get("ARROW_LOG_HELPER_DATA_DIR") or "/arrow-log-helper-data"
        self._launch_cwd = os.environ.get("ARROW_LOG_HELPER_LAUNCH_CWD") or self._data_dir

        # Safety check: must be started via arrow_log_helper.__main__ (zip/module) so firewall is active.
        if (not write_firewall.is_installed()) or (not os.path.isdir(self._data_dir)):
            try:
                messagebox.showerror(
                    "Safety check failed",
                    "Arrow Log Helper must start via the zip/module entrypoint so the write firewall is enabled.\n\n"
                    "Expected writable DATA_DIR: %s\n"
                    "Firewall installed: %s"
                    % (_safe_text(self._data_dir), _safe_text(write_firewall.is_installed())),
                )
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass
            raise SystemExit(2)

        demo_root = os.environ.get("ARROW_LOG_HELPER_DEMO_ROOT")
        self._demo_root = demo_root

        roots = self._initial_roots()

        self._settings = {
            "roots": roots,
            "include_ext": list(DEFAULT_INCLUDE_EXT),
            "exclude_dirs": list(DEFAULT_EXCLUDE_DIRS),
            # Real machine mode defaults: unlimited results/time/files unless set.
            "max_results": None,
            "max_file_bytes": int(DEFAULT_MAX_FILE_BYTES),
            "max_seconds": None,
            "max_files_scanned": None,
            "progress_every_n_files": int(DEFAULT_PROGRESS_EVERY_N_FILES),
            "context_fallback": 50,
            "case_insensitive": False,
            "follow_symlinks": False,
        }

        self._result = None
        self._selected_index = None
        self._discover_results = []
        
        # New instance variables for refactored UI
        self.current_roots = roots
        self.current_result = None
        self.current_bundle = None
        self.selected_match_idx = None

        self._build_ui()
        self._set_status("Ready")

    def _split_pathsep(self, s):
        s = s or ""
        s = s.strip()
        if not s:
            return []
        # Primary: os.pathsep. Also tolerate ';' on Linux if user pasted it.
        if os.pathsep in s:
            parts = s.split(os.pathsep)
        elif (";" in s) and (os.pathsep != ";"):
            parts = s.split(";")
        else:
            parts = [s]
        return [p.strip() for p in parts if p.strip()]

    def _initial_roots(self):
        # 1) DEMO override
        if self._demo_root:
            return [self._demo_root]

        # 2) Explicit roots env override
        roots_env = os.environ.get("ARROW_LOG_HELPER_ROOTS")
        if roots_env:
            parts = self._split_pathsep(roots_env)
            # Resolve relative roots against launch cwd for portability.
            out = []
            for p in parts:
                if p == ".":
                    out.append(self._launch_cwd)
                elif os.path.isabs(p):
                    out.append(p)
                else:
                    out.append(os.path.abspath(os.path.join(self._launch_cwd, p)))
            return out

        # 3) Persisted selection
        saved = config_store.load_selected_roots(self._data_dir)
        if saved:
            return saved

        # 4) Safe default
        if os.name == "nt":
            # Dev-friendly default
            return [self._launch_cwd]
        return ["/opt/memjet"]

    def _build_ui(self):
        # Configure grid weights for expansion
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # -------- Row 0: Top Bar --------
        top_bar = tk.Frame(self.root)
        top_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_columnconfigure(3, weight=2)
        
        # Left: Scan roots
        tk.Label(top_bar, text="Scan roots:").grid(row=0, column=0, padx=(0, 4), sticky="w")
        self.roots_entry_var = tk.StringVar()
        self.roots_entry = tk.Entry(top_bar, textvariable=self.roots_entry_var, state="readonly", width=40)
        self.roots_entry.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        self._update_roots_display()
        
        self.btn_change_roots = tk.Button(top_bar, text="Change...", command=self.on_change_roots)
        self.btn_change_roots.grid(row=0, column=2, padx=(0, 16))
        
        # Middle: Log entry
        tk.Label(top_bar, text="Log:").grid(row=0, column=3, padx=(0, 4), sticky="w")
        self.log_entry_var = tk.StringVar()
        self.log_entry = tk.Entry(top_bar, textvariable=self.log_entry_var, width=50)
        self.log_entry.grid(row=0, column=4, padx=(0, 8), sticky="ew")
        self.log_entry.bind("<Return>", lambda e: self.on_analyze())
        self.log_entry.bind("<KeyRelease>", self._on_log_entry_change)
        
        self.btn_analyze = tk.Button(top_bar, text="Analyze", command=self.on_analyze, state="disabled")
        self.btn_analyze.grid(row=0, column=5, padx=(0, 8))
        
        self.btn_export = tk.Button(top_bar, text="Export JSON", command=self.on_export_json, state="disabled")
        self.btn_export.grid(row=0, column=6, padx=(0, 8))
        
        self.btn_copy_json = tk.Button(top_bar, text="Copy JSON", command=self.on_copy_json, state="disabled")
        self.btn_copy_json.grid(row=0, column=7, padx=(0, 8))
        
        # Right: Help
        self.btn_help = tk.Button(top_bar, text="Help", command=self.on_help)
        self.btn_help.grid(row=0, column=8, padx=(0, 0))
        
        # -------- Row 1: Main Area (PanedWindow) --------
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        
        # Left pane: Match list
        left_frame = tk.Frame(main_paned)
        main_paned.add(left_frame, minsize=300, width=300)
        
        tk.Label(left_frame, text="Matches").pack(side=tk.TOP, anchor="w", pady=(0, 4))
        
        list_frame = tk.Frame(left_frame)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Treeview for matches
        self.matches_tree = ttk.Treeview(
            list_frame,
            columns=("%", "Type", "Component", "Location"),
            show="headings",
            selectmode="browse",
        )
        self.matches_tree.heading("%", text="%")
        self.matches_tree.heading("Type", text="Type")
        self.matches_tree.heading("Component", text="Component")
        self.matches_tree.heading("Location", text="Location")
        self.matches_tree.column("%", width=50, anchor="e")
        self.matches_tree.column("Type", width=100)
        self.matches_tree.column("Component", width=120)
        self.matches_tree.column("Location", width=200)
        
        matches_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.matches_tree.yview)
        self.matches_tree.configure(yscrollcommand=matches_scroll.set)
        
        self.matches_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        matches_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.matches_tree.bind("<<TreeviewSelect>>", self.on_match_selected)
        
        # Right pane: Detail panel (vertical paned window)
        right_paned = tk.PanedWindow(main_paned, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        main_paned.add(right_paned, minsize=500)
        
        # Top: Summary section
        summary_frame = tk.Frame(right_paned)
        right_paned.add(summary_frame, minsize=120, height=120)
        
        tk.Label(summary_frame, text="Summary").pack(side=tk.TOP, anchor="w", pady=(0, 4))
        summary_text_frame = tk.Frame(summary_frame)
        summary_text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.summary_text = tk.Text(summary_text_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        summary_text_scroll = tk.Scrollbar(summary_text_frame, orient=tk.VERTICAL, command=self.summary_text.yview)
        self.summary_text.configure(yscrollcommand=summary_text_scroll.set)
        self.summary_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        summary_text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Middle: Metadata section
        metadata_frame = tk.Frame(right_paned)
        right_paned.add(metadata_frame, minsize=150, height=150)
        
        tk.Label(metadata_frame, text="Metadata").pack(side=tk.TOP, anchor="w", pady=(0, 4))
        metadata_tree_frame = tk.Frame(metadata_frame)
        metadata_tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.metadata_tree = ttk.Treeview(
            metadata_tree_frame,
            columns=("Value",),
            show="tree headings",
            selectmode="browse",
        )
        self.metadata_tree.heading("#0", text="Key")
        self.metadata_tree.heading("Value", text="Value")
        self.metadata_tree.column("#0", width=200)
        self.metadata_tree.column("Value", width=300)
        
        metadata_scroll = ttk.Scrollbar(metadata_tree_frame, orient=tk.VERTICAL, command=self.metadata_tree.yview)
        self.metadata_tree.configure(yscrollcommand=metadata_scroll.set)
        
        self.metadata_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        metadata_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.metadata_tree.bind("<Double-1>", self.on_metadata_double_click)
        
        # Bottom: Notebook tabs
        notebook_frame = tk.Frame(right_paned)
        right_paned.add(notebook_frame, minsize=200)
        
        self.detail_notebook = ttk.Notebook(notebook_frame)
        self.detail_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Tab 1: Code Block
        code_block_frame = tk.Frame(self.detail_notebook)
        self.detail_notebook.add(code_block_frame, text="Code Block")
        code_block_text_frame = tk.Frame(code_block_frame)
        code_block_text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        self.code_block_text = tk.Text(code_block_text_frame, wrap=tk.NONE, state=tk.DISABLED)
        try:
            self.code_block_text.config(font=("Courier", 10))
        except Exception:
            pass
        code_block_scroll_v = tk.Scrollbar(code_block_text_frame, orient=tk.VERTICAL, command=self.code_block_text.yview)
        code_block_scroll_h = tk.Scrollbar(code_block_text_frame, orient=tk.HORIZONTAL, command=self.code_block_text.xview)
        self.code_block_text.configure(yscrollcommand=code_block_scroll_v.set, xscrollcommand=code_block_scroll_h.set)
        self.code_block_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        code_block_scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
        code_block_scroll_h.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Tab 2: Matched Line
        matched_line_frame = tk.Frame(self.detail_notebook)
        self.detail_notebook.add(matched_line_frame, text="Matched Line")
        matched_line_text_frame = tk.Frame(matched_line_frame)
        matched_line_text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        self.matched_line_text = tk.Text(matched_line_text_frame, wrap=tk.NONE, state=tk.DISABLED)
        try:
            self.matched_line_text.config(font=("Courier", 10))
        except Exception:
            pass
        matched_line_scroll_v = tk.Scrollbar(matched_line_text_frame, orient=tk.VERTICAL, command=self.matched_line_text.yview)
        matched_line_scroll_h = tk.Scrollbar(matched_line_text_frame, orient=tk.HORIZONTAL, command=self.matched_line_text.xview)
        self.matched_line_text.configure(yscrollcommand=matched_line_scroll_v.set, xscrollcommand=matched_line_scroll_h.set)
        self.matched_line_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        matched_line_scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
        matched_line_scroll_h.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Tab 3: Raw JSON
        raw_json_frame = tk.Frame(self.detail_notebook)
        self.detail_notebook.add(raw_json_frame, text="Raw JSON")
        raw_json_text_frame = tk.Frame(raw_json_frame)
        raw_json_text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        self.raw_json_text = tk.Text(raw_json_text_frame, wrap=tk.NONE, state=tk.DISABLED)
        try:
            self.raw_json_text.config(font=("Courier", 9))
        except Exception:
            pass
        raw_json_scroll_v = tk.Scrollbar(raw_json_text_frame, orient=tk.VERTICAL, command=self.raw_json_text.yview)
        raw_json_scroll_h = tk.Scrollbar(raw_json_text_frame, orient=tk.HORIZONTAL, command=self.raw_json_text.xview)
        self.raw_json_text.configure(yscrollcommand=raw_json_scroll_v.set, xscrollcommand=raw_json_scroll_h.set)
        self.raw_json_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        raw_json_scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
        raw_json_scroll_h.pack(side=tk.BOTTOM, fill=tk.X)
        
        # -------- Row 2: Status Bar --------
        status_bar = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        status_bar.grid(row=2, column=0, sticky="ew")
        status_bar.grid_columnconfigure(0, weight=1)

        self.status_var = tk.StringVar()
        self.status_label = tk.Label(status_bar, textvariable=self.status_var, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        
        safety_label = tk.Label(status_bar, text="Read-only: no files modified", anchor="e")
        safety_label.grid(row=0, column=1, padx=6, pady=4)

    def _update_roots_display(self):
        """Update the read-only roots entry display."""
        roots_text = "; ".join([_safe_text(r) for r in self.current_roots]) if self.current_roots else "(none)"
        self.roots_entry_var.set(roots_text)
    
    def _on_log_entry_change(self, event=None):
        """Enable/disable Analyze button based on log entry content."""
        text = self.log_entry_var.get().strip()
        if text:
            self.btn_analyze.config(state="normal")
        else:
            self.btn_analyze.config(state="disabled")

    def _resolve_base(self, b):
        b = (b or "").strip()
        if not b:
            return None
        if b == ".":
            return self._launch_cwd
        if os.path.isabs(b):
            return b
        return os.path.abspath(os.path.join(self._launch_cwd, b))

    def on_discover_roots(self):
        bases_raw = _safe_text(self.discovery_bases_var.get())
        bases = self._split_pathsep(bases_raw)
        resolved = []
        for b in bases:
            rb = self._resolve_base(b)
            if rb:
                resolved.append(rb)

        if not resolved:
            messagebox.showerror("Discovery", "No valid discovery bases provided.")
            return

        if self.allow_root_var.get() == 0:
            for p in resolved:
                if repo_discover.safe_is_massive_root(p):
                    messagebox.showerror(
                        "Discovery",
                        "Refusing to scan massive root %r unless you check the 'Allow scanning filesystem root /' box."
                        % (p,),
                    )
                    return

        def progress_cb(info):
            try:
                self._set_status("Discovering... %s dirs (now: %s)" % (info.get("dirs_visited"), info.get("current_dir")))
                self.root.update_idletasks()
            except Exception:
                pass

        self._set_status("Discovering...")
        try:
            self.root.update_idletasks()
        except Exception:
            pass

        try:
            results = repo_discover.discover_candidates(
                resolved,
                max_depth=6,
                exclude_dir_names=None,
                follow_symlinks=False,
                progress_cb=progress_cb,
            )
        except Exception as e:
            messagebox.showerror("Discovery error", _safe_text(e))
            self._set_status("Idle")
            return

        self._discover_results = results or []
        try:
            self.discover_list.delete(0, tk.END)
            for c in self._discover_results:
                score = int(c.get("score", 0))
                git = "Y" if c.get("git") else "N"
                code_n = int(c.get("code_files_here", 0))
                path = _safe_text(c.get("path", ""))
                row = "%4d  %s  %4d  %s" % (score, git, code_n, path)
                self.discover_list.insert(tk.END, row)
        except Exception:
            pass
        self._set_status("Discovery complete: %d candidates" % (len(self._discover_results),))

    def on_use_selected_root(self):
        try:
            sel = self.discover_list.curselection()
            if not sel:
                messagebox.showerror("Select root", "Select a candidate root first.")
                return
            idx = int(sel[0])
        except Exception:
            return
        if idx < 0 or idx >= len(self._discover_results):
            return
        path = self._discover_results[idx].get("path")
        if not path:
            return

        # Persist and apply.
        try:
            config_store.save_selected_roots(self._data_dir, [path])
        except Exception as e:
            messagebox.showerror("Save failed", _safe_text(e))
            return

        self._settings["roots"] = [path]
        self._refresh_settings_summary()
        self._refresh_banner()
        self._set_status("Using root: %s" % (_safe_text(path),))

    def _set_status(self, text):
        self.status_var.set(_safe_text(text))

    def _get_input(self):
        return self.log_entry_var.get().strip()

    def _set_text_readonly(self, widget, text):
        try:
            widget.config(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert("1.0", _safe_text(text))
            widget.config(state=tk.DISABLED)
        except Exception:
            # Last resort: don't crash the UI.
            pass

    def _get_selected_match(self):
        """Get currently selected match from current_result (legacy compatibility)."""
        if not self.current_result:
            return None
        matches = self.current_result.get("matches") or []
        if self.selected_match_idx is None:
            return None
        if self.selected_match_idx < 0 or self.selected_match_idx >= len(matches):
            return None
        return matches[self.selected_match_idx]

    def on_analyze(self):
        log_text = self.log_entry_var.get().strip()
        if not log_text:
            return
        
        # Determine roots
        if self._demo_root:
            roots = [self._demo_root]
        elif self.current_roots:
            roots = self.current_roots
        else:
            roots = self._settings.get("roots", [])
        
        # Update settings with current roots
        settings = dict(self._settings)
        settings["roots"] = roots
        
        # Disable Analyze button
        self.btn_analyze.config(state="disabled")
        self._set_status("Scanning...")
        try:
            self.root.update_idletasks()
        except Exception:
            pass

        # Progress callback with cooperative updates
        progress_queue = []
        
        def progress_cb(stats):
            progress_queue.append(dict(stats))
            # Schedule UI update
            self.root.after(10, _process_progress)
        
        def _process_progress():
            if progress_queue:
                stats = progress_queue.pop(0)
                try:
                    files_scanned = int(stats.get("files_scanned", 0))
                    hits_found = int(stats.get("hits_found", 0))
                    elapsed = float(stats.get("elapsed_seconds", 0.0))
                    msg = "Scanning... %d files, %d hits, %.1fs" % (files_scanned, hits_found, elapsed)
                stopped = stats.get("stopped_reason")
                if stopped:
                    msg += " (stopped: %s)" % (_safe_text(stopped),)
                self._set_status(msg)
                except Exception:
                    pass
            if progress_queue:
                self.root.after(10, _process_progress)

        try:
            result = analyzer.analyze(log_text, settings, progress_cb=progress_cb)
        except Exception as e:
            self._set_status("Ready")
            self.btn_analyze.config(state="normal")
            messagebox.showerror("Analyzer error", _safe_text(e))
            return

        # Process remaining progress updates
        while progress_queue:
            _process_progress()
            self.root.update_idletasks()
        
        # Store result
        self.current_result = result or {"parsed": {}, "matches": [], "scan_stats": {}}
        self._result = self.current_result  # Keep for compatibility
        
        # Build UI bundle
        matches = self.current_result.get("matches") or []
        if matches:
            self.current_bundle = ui_bundle.build_ui_bundle(self.current_result, 0)
            self.selected_match_idx = 0
        else:
            self.current_bundle = ui_bundle.build_ui_bundle(self.current_result, None)
            self.selected_match_idx = None
        
        # Populate match list Treeview
        self._populate_match_list()
        
        # Update detail panels
        self._update_detail_panels()
        
        # Enable Export/Copy buttons
        self.btn_export.config(state="normal")
        self.btn_copy_json.config(state="normal")
        self.btn_analyze.config(state="normal")
        
        # Update status
        scan_stats = self.current_result.get("scan_stats") or {}
        elapsed = scan_stats.get("elapsed_seconds")
        hits = len(matches)
        try:
            elapsed = float(elapsed) if elapsed is not None else None
        except Exception:
            elapsed = None
        if elapsed is not None:
            msg = "Done in %.1fs, hits=%d" % (elapsed, hits)
        else:
            msg = "Done, hits=%d" % (hits,)
        stopped = scan_stats.get("stopped_reason")
        if stopped:
            msg += " (stopped: %s)" % (_safe_text(stopped),)
        self._set_status(msg)

    def _populate_match_list(self):
        """Populate the match list Treeview."""
        # Clear existing items
        for item in self.matches_tree.get_children():
            self.matches_tree.delete(item)
        
        if not self.current_bundle:
            self.matches_tree.insert("", tk.END, values=("", "", "", "No matches found"))
            return
        
        matches = self.current_bundle.get("matches") or []
        if not matches:
            self.matches_tree.insert("", tk.END, values=("", "", "", "No matches found"))
            return
        
        # Insert matches (already sorted by score desc from bundle)
        for idx, match in enumerate(matches):
            confidence = match.get("confidence_percent", 0)
            match_type = match.get("match_type", "-")
            component = match.get("component") or "-"
            location = match.get("location_short", "-")
            
            self.matches_tree.insert("", tk.END, iid=str(idx), values=(
                str(confidence),
                _safe_text(match_type),
                _safe_text(component),
                _safe_text(location),
            ))
        
        # Auto-select first match
        if matches:
            self.matches_tree.selection_set("0")
            self.matches_tree.focus("0")
            self.matches_tree.see("0")

    def on_match_selected(self, event=None):
        """Handle match selection from Treeview."""
        if not self.current_bundle:
            return
        
        selection = self.matches_tree.selection()
        if not selection:
            return
        
        try:
            idx = int(selection[0])
        except Exception:
            return
        
        matches = self.current_bundle.get("matches") or []
        if idx < 0 or idx >= len(matches):
            return
        
        # Rebuild bundle with selected match
        self.selected_match_idx = idx
        self.current_bundle = ui_bundle.build_ui_bundle(self.current_result, idx)
        self._selected_index = idx  # Keep for compatibility
        
        # Update detail panels
        self._update_detail_panels()
    
    def _update_detail_panels(self):
        """Update all detail panels (summary, metadata, tabs)."""
        if not self.current_bundle:
            self._set_text_readonly(self.summary_text, "")
            self._clear_metadata_tree()
            self._set_text_readonly(self.code_block_text, "")
            self._set_text_readonly(self.matched_line_text, "")
            self._set_text_readonly(self.raw_json_text, "")
            return
        
        selected = self.current_bundle.get("selected")
        
        # Update Summary
        if selected:
            summary = selected.get("summary_text", "")
        else:
            summary = "No match selected."
        self._set_text_readonly(self.summary_text, summary)
        
        # Update Metadata Treeview
        self._populate_metadata_tree()
        
        # Update Code Block tab
        if selected:
            # Try to get enclosure block
            enclosure_type = selected.get("enclosure_type")
            if enclosure_type and enclosure_type != "none":
                # Try to read the actual block from file
                path = selected.get("path")
                start_line = selected.get("start_line")
                end_line = selected.get("end_line")
                if path and start_line and end_line:
                    try:
                        block = self._read_file_lines(path, start_line, end_line)
                        self._set_text_readonly(self.code_block_text, block)
                    except Exception:
                        # Fallback to signature or context
                        sig = selected.get("signature") or selected.get("context_preview") or ""
                        self._set_text_readonly(self.code_block_text, sig)
                else:
                    sig = selected.get("signature") or selected.get("context_preview") or ""
                    self._set_text_readonly(self.code_block_text, sig)
            else:
                context = selected.get("context_preview") or ""
                self._set_text_readonly(self.code_block_text, context)
        else:
            self._set_text_readonly(self.code_block_text, "")
        
        # Update Matched Line tab
        if selected:
            line_text = selected.get("line_text", "")
            self._set_text_readonly(self.matched_line_text, line_text)
        else:
            self._set_text_readonly(self.matched_line_text, "")
        
        # Update Raw JSON tab
        json_str = ui_bundle.pretty_json(self.current_bundle)
        self._set_text_readonly(self.raw_json_text, json_str)
    
    def _read_file_lines(self, path, start_line, end_line):
        """Read lines from file (for code block display)."""
        try:
            with open(path, "rb") as f:
                lines = f.readlines()
            # Convert to strings
            text_lines = []
            for i, line in enumerate(lines, 1):
                if start_line <= i <= end_line:
                    try:
                        text_lines.append(line.decode("utf-8", "replace"))
                    except Exception:
                        text_lines.append(str(line))
            return "".join(text_lines)
        except Exception:
            return ""
    
    def _populate_metadata_tree(self):
        """Populate metadata Treeview with key/value pairs."""
        # Clear existing
        self._clear_metadata_tree()
        
        if not self.current_bundle:
            return
        
        selected = self.current_bundle.get("selected")
        parsed = self.current_bundle.get("parsed") or {}
        scan = self.current_bundle.get("scan") or {}
        
        # Add parsed fields
        for key in ("timestamp", "host_or_serial", "process", "level", "thread", "component", "message"):
            if key in parsed:
                value = _safe_text(parsed[key])
                if len(value) > 60:
                    value = value[:57] + "..."
                self.metadata_tree.insert("", tk.END, text=_safe_text(key), values=(value,))
        
        # Add selected match fields
        if selected:
            for key in ("match_type", "name", "path", "line_no", "score", "enclosure_type"):
                if key in selected:
                    value = _safe_text(selected[key])
                    if len(value) > 60:
                        value = value[:57] + "..."
                    self.metadata_tree.insert("", tk.END, text="match.%s" % (_safe_text(key),), values=(value,))
        
        # Add scan stats
        for key in ("files_scanned", "hits_found", "elapsed_seconds", "stopped_reason"):
            if key in scan:
                value = _safe_text(scan[key])
                if len(value) > 60:
                    value = value[:57] + "..."
                self.metadata_tree.insert("", tk.END, text="scan.%s" % (_safe_text(key),), values=(value,))
    
    def _clear_metadata_tree(self):
        """Clear metadata Treeview."""
        for item in self.metadata_tree.get_children():
            self.metadata_tree.delete(item)
    
    def on_metadata_double_click(self, event=None):
        """Show full value in modal on double-click."""
        selection = self.metadata_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        key = self.metadata_tree.item(item, "text")
        values = self.metadata_tree.item(item, "values")
        value = values[0] if values else ""
        
        # Get full value from bundle
        full_value = self._get_full_metadata_value(key)
        if full_value is None:
            full_value = value
        
        # Show modal
        dialog = tk.Toplevel(self.root)
        dialog.title("Metadata: %s" % (_safe_text(key),))
        dialog.transient(self.root)
        dialog.grab_set()
        
        content = tk.Frame(dialog, padx=12, pady=12)
        content.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(content, text="Key:").pack(anchor="w")
        key_text = tk.Text(content, height=1, wrap=tk.WORD, state=tk.DISABLED)
        key_text.pack(fill=tk.X, pady=(0, 8))
        self._set_text_readonly(key_text, _safe_text(key))
        
        tk.Label(content, text="Value:").pack(anchor="w")
        value_text = tk.Text(content, height=10, wrap=tk.WORD, state=tk.DISABLED)
        value_scroll = tk.Scrollbar(content, orient=tk.VERTICAL, command=value_text.yview)
        value_text.configure(yscrollcommand=value_scroll.set)
        value_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        value_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._set_text_readonly(value_text, _safe_text(full_value))
        
        tk.Button(content, text="Close", command=dialog.destroy).pack(pady=(8, 0))
        
        dialog.geometry("500x400")
    
    def _get_full_metadata_value(self, key):
        """Get full value for metadata key from bundle."""
        if not self.current_bundle:
            return None
        
        # Parse key (may be "match.field" or "scan.field")
        if key.startswith("match."):
            field = key[6:]
            selected = self.current_bundle.get("selected") or {}
            return selected.get(field)
        elif key.startswith("scan."):
            field = key[5:]
            scan = self.current_bundle.get("scan") or {}
            return scan.get(field)
        else:
            parsed = self.current_bundle.get("parsed") or {}
            return parsed.get(key)

    def on_clear(self):
        """Clear all data (legacy method, may not be used in new UI)."""
        self.current_result = None
        self.current_bundle = None
        self.selected_match_idx = None
        self._result = None
        self._selected_index = None
        try:
            self.log_entry_var.set("")
        except Exception:
            pass
        self._populate_match_list()
        self._update_detail_panels()
        self.btn_export.config(state="disabled")
        self.btn_copy_json.config(state="disabled")
        self._set_status("Ready")

    def _build_report_text(self):
        lines = []

        if self._result:
            lines.append("Selected line")
            lines.append("-------------")
            lines.append(_safe_text(self._result.get("selected_line", "")))
            lines.append("")

        parsed = (self._result or {}).get("parsed") or {}
        if parsed:
            lines.append("Parsed")
            lines.append("------")
            for k in ("timestamp", "host_or_serial", "process", "level", "thread", "component", "message"):
                if k in parsed:
                    lines.append("%s: %s" % (k, _safe_text(parsed.get(k))))
            lines.append("")

        if self._result:
            lines.append("Keys")
            lines.append("----")
            lines.append("key_exact: %s" % (_safe_text(self._result.get("key_exact", "")),))
            lines.append("key_normalized: %s" % (_safe_text(self._result.get("key_normalized", "")),))
            lines.append("tokens: %s" % (_safe_text(self._result.get("tokens", [])),))
            lines.append("")

        match = self._get_selected_match()
        if match:
            lines.append("Selected Match")
            lines.append("--------------")
            lines.append("match_type: %s" % (_safe_text(match.get("match_type")),))
            lines.append("name: %s" % (_safe_text(match.get("name")),))
            lines.append("component: %s" % (_safe_text(match.get("component")),))
            lines.append("path: %s:%s" % (_safe_text(match.get("path")), _safe_text(match.get("line_no"))))
            lines.append("")
            lines.append("Matched Line")
            lines.append("------------")
            lines.append(_safe_text(match.get("line_text", "")))
            lines.append("")
            lines.append("Signature / Context")
            lines.append("-------------------")
            if match.get("signature"):
                lines.append(_safe_text(match.get("signature")))
            else:
                lines.append(_safe_text(match.get("context_preview", "")))
            lines.append("")
        else:
            lines.append("(No match selected)")
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def on_copy_report(self):
        report = self._build_report_text()
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(report)
            self._set_status("Copied report to clipboard")
        except Exception as e:
            messagebox.showerror("Clipboard error", _safe_text(e))
    
    def on_change_roots(self):
        """Open root selection modal dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Scan Roots")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Main content frame
        content = tk.Frame(dialog, padx=12, pady=12)
        content.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(content, text="Enter one root path per line:").pack(anchor="w", pady=(0, 4))
        
        roots_text = tk.Text(content, height=8, width=60)
        roots_text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        roots_text.insert("1.0", "\n".join(self.current_roots) if self.current_roots else "")
        
        # Buttons frame
        btn_frame = tk.Frame(content)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        
        def use_these_roots():
            text = roots_text.get("1.0", tk.END).strip()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            
            # Validate each root
            validated = []
            for root_path in lines:
                if not root_path:
                    continue
                # Resolve relative paths
                if root_path == ".":
                    resolved = self._launch_cwd
                elif os.path.isabs(root_path):
                    resolved = root_path
                else:
                    resolved = os.path.abspath(os.path.join(self._launch_cwd, root_path))
                
                # Check if directory exists
                if not os.path.isdir(resolved):
                    messagebox.showerror("Invalid root", "Not a directory: %s" % (_safe_text(root_path),))
                    return
                
                # Warn about massive root
                if repo_discover.safe_is_massive_root(resolved):
                    result = messagebox.askyesno(
                        "Warning",
                        "Scanning root %s can take a very long time.\n\nContinue anyway?" % (_safe_text(resolved),),
                        default=messagebox.NO,
                    )
                    if not result:
                        return
                
                validated.append(resolved)
            
            if not validated:
                messagebox.showerror("No roots", "At least one valid root directory is required.")
                return
            
            # Apply roots
            self.current_roots = validated
            self._settings["roots"] = validated
            self._update_roots_display()
            
            # Optionally save to config
            try:
                config_store.save_selected_roots(self._data_dir, validated)
            except Exception:
                pass  # Non-fatal
            
            dialog.destroy()
        
        def use_demo_root():
            demo_root = os.environ.get("ARROW_LOG_HELPER_DEMO_ROOT")
            if not demo_root:
                messagebox.showerror("Demo root not set", "ARROW_LOG_HELPER_DEMO_ROOT environment variable is not set.")
                return
            if not os.path.isdir(demo_root):
                messagebox.showerror("Invalid demo root", "Demo root is not a directory: %s" % (_safe_text(demo_root),))
                return
            roots_text.delete("1.0", tk.END)
            roots_text.insert("1.0", demo_root)
        
        def discover_roots():
            # Simple discovery - reuse existing logic
            bases = ["/opt", "/home", "/usr/local"]
            if os.name == "nt":
                bases = ["."]
            
            def progress_cb(info):
                try:
                    self._set_status("Discovering... %s dirs" % (info.get("dirs_visited", 0),))
                    dialog.update_idletasks()
                except Exception:
                    pass
            
            try:
                results = repo_discover.discover_candidates(
                    bases,
                    max_depth=4,
                    exclude_dir_names=None,
                    follow_symlinks=False,
                    progress_cb=progress_cb,
                )
            except Exception as e:
                messagebox.showerror("Discovery error", _safe_text(e))
                return
            
            if results:
                # Show top 5 results
                top_paths = [r.get("path") for r in results[:5] if r.get("path")]
                if top_paths:
                    roots_text.delete("1.0", tk.END)
                    roots_text.insert("1.0", "\n".join(top_paths))
                else:
                    messagebox.showinfo("Discovery", "No candidate roots found.")
            else:
                messagebox.showinfo("Discovery", "No candidate roots found.")
        
        tk.Button(btn_frame, text="Use These Roots", command=use_these_roots).pack(side=tk.LEFT, padx=(0, 8))
        
        if os.environ.get("ARROW_LOG_HELPER_DEMO_ROOT"):
            tk.Button(btn_frame, text="Use Demo Root", command=use_demo_root).pack(side=tk.LEFT, padx=(0, 8))
        
        try:
            if repo_discover:
                tk.Button(btn_frame, text="Discover...", command=discover_roots).pack(side=tk.LEFT, padx=(0, 8))
        except Exception:
            pass  # repo_discover not available
        
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT)
        
        dialog.geometry("500x300")
        dialog.resizable(True, True)
    
    def on_help(self):
        """Show help modal."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Help")
        dialog.transient(self.root)
        dialog.grab_set()
        
        content = tk.Frame(dialog, padx=16, pady=16)
        content.pack(fill=tk.BOTH, expand=True)
        
        help_text = """Arrow Log Helper (POC)

Read-only scanning: no files under printer software directories are modified.

Tool writes only to its own data directory:
%s

If scanning root / is selected, it may take a long time.

Usage:
1. Set scan roots (or use demo root)
2. Paste log line in the Log field
3. Click Analyze
4. Select matches from the list to view details
5. Export or copy JSON results as needed""" % (_safe_text(self._data_dir),)
        
        text_widget = tk.Text(content, wrap=tk.WORD, width=60, height=12, padx=8, pady=8)
        text_widget.insert("1.0", help_text)
        text_widget.config(state=tk.DISABLED)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        tk.Button(content, text="Close", command=dialog.destroy).pack(pady=(8, 0))
        
        dialog.geometry("500x300")
    
    def on_export_json(self):
        """Export current bundle as JSON to DATA_DIR."""
        if not self.current_bundle:
            messagebox.showerror("No data", "No analysis result to export.")
            return
        
        try:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = "arrow_log_helper_result_%s.json" % (timestamp,)
            filepath = os.path.join(self._data_dir, filename)
            
            # Ensure DATA_DIR exists and is writable
            if not os.path.isdir(self._data_dir):
                try:
                    os.makedirs(self._data_dir)
                except Exception as e:
                    messagebox.showerror("Export failed", "Cannot create data directory: %s" % (_safe_text(e),))
                    return
            
            # Atomic write
            tmp_path = filepath + ".tmp"
            with open(tmp_path, "wb") as f:
                json_str = ui_bundle.pretty_json(self.current_bundle)
                try:
                    f.write(json_str.encode("utf-8"))
                except Exception:
                    f.write(json_str)
            
            # Rename (atomic on POSIX, best-effort on Windows)
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            os.rename(tmp_path, filepath)
            
            messagebox.showinfo("Export successful", "JSON exported to:\n%s" % (_safe_text(filepath),))
        except Exception as e:
            messagebox.showerror("Export failed", "Failed to export JSON: %s" % (_safe_text(e),))
    
    def on_copy_json(self):
        """Copy current bundle as pretty JSON to clipboard."""
        if not self.current_bundle:
            messagebox.showerror("No data", "No analysis result to copy.")
            return
        
        try:
            json_str = ui_bundle.pretty_json(self.current_bundle)
            self.root.clipboard_clear()
            self.root.clipboard_append(json_str)
            self._set_status("JSON copied")
        except Exception as e:
            messagebox.showerror("Copy failed", "Failed to copy JSON: %s" % (_safe_text(e),))


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    root = tk.Tk()
    ArrowLogHelperApp(root)
    root.minsize(1100, 700)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())


