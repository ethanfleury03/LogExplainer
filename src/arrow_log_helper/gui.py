from __future__ import absolute_import, print_function

import os
import sys

try:
    import Tkinter as tk  # Python 2
    import tkMessageBox as messagebox
except ImportError:  # pragma: no cover (py3 fallback)
    import tkinter as tk  # type: ignore
    from tkinter import messagebox  # type: ignore


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
        self.root.title("Arrow Log Helper")

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

        self._build_ui()
        self._set_status("Idle")

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
        # -------- Top: input + buttons --------
        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        self.banner_var = tk.StringVar()
        banner = tk.Label(top, textvariable=self.banner_var, anchor="w", justify=tk.LEFT)
        banner.pack(side=tk.TOP, anchor="w")
        self._refresh_banner()

        # -------- Start: repo scanner --------
        start = tk.Frame(top, bd=1, relief=tk.GROOVE)
        start.pack(side=tk.TOP, fill=tk.X, pady=(6, 8))

        start_title = tk.Label(start, text="Start (Repo Scanner)")
        start_title.pack(side=tk.TOP, anchor="w", padx=6, pady=(6, 2))

        bases_row = tk.Frame(start)
        bases_row.pack(side=tk.TOP, fill=tk.X, padx=6)

        tk.Label(bases_row, text="Discovery bases").pack(side=tk.LEFT)

        self.discovery_bases_var = tk.StringVar()
        if os.name == "nt":
            self.discovery_bases_var.set(".")
        else:
            self.discovery_bases_var.set(os.pathsep.join(["/opt", "/home", "/usr/local"]))
        self.discovery_bases_entry = tk.Entry(bases_row, textvariable=self.discovery_bases_var, width=60)
        self.discovery_bases_entry.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)

        opts_row = tk.Frame(start)
        opts_row.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(4, 0))

        self.allow_root_var = tk.IntVar()
        self.allow_root_var.set(0)
        tk.Checkbutton(
            opts_row,
            text="Allow scanning filesystem root / (slow)",
            variable=self.allow_root_var,
        ).pack(side=tk.LEFT)

        btns_row = tk.Frame(start)
        btns_row.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 6))

        self.btn_discover = tk.Button(btns_row, text="Discover codebase roots", command=self.on_discover_roots)
        self.btn_discover.pack(side=tk.LEFT)

        self.btn_use_root = tk.Button(btns_row, text="Use selected root(s)", command=self.on_use_selected_root)
        self.btn_use_root.pack(side=tk.LEFT, padx=(6, 0))

        results_frame = tk.Frame(start)
        results_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=6, pady=(0, 6))

        self.discover_scroll = tk.Scrollbar(results_frame, orient=tk.VERTICAL)
        self.discover_list = tk.Listbox(
            results_frame,
            height=6,
            yscrollcommand=self.discover_scroll.set,
            exportselection=False,
        )
        self.discover_scroll.config(command=self.discover_list.yview)
        self.discover_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.discover_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        lbl = tk.Label(top, text="Paste log line or block")
        lbl.pack(side=tk.TOP, anchor="w")

        self.input_text = tk.Text(top, height=8, wrap=tk.WORD)
        self.input_text.pack(side=tk.TOP, fill=tk.X, expand=False, pady=(4, 6))

        btn_row = tk.Frame(top)
        btn_row.pack(side=tk.TOP, fill=tk.X)

        self.btn_analyze = tk.Button(btn_row, text="Analyze", command=self.on_analyze)
        self.btn_analyze.pack(side=tk.LEFT)

        self.btn_clear = tk.Button(btn_row, text="Clear", command=self.on_clear)
        self.btn_clear.pack(side=tk.LEFT, padx=(6, 0))

        self.btn_copy = tk.Button(btn_row, text="Copy Report", command=self.on_copy_report)
        self.btn_copy.pack(side=tk.LEFT, padx=(6, 0))

        # -------- Middle: paned window --------
        mid = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Left: matches list
        left = tk.Frame(mid)
        mid.add(left, minsize=220)

        left_lbl = tk.Label(left, text="Matches")
        left_lbl.pack(side=tk.TOP, anchor="w")

        left_list_frame = tk.Frame(left)
        left_list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(4, 0))

        self.matches_scroll = tk.Scrollbar(left_list_frame, orient=tk.VERTICAL)
        self.matches_list = tk.Listbox(
            left_list_frame,
            yscrollcommand=self.matches_scroll.set,
            exportselection=False,
        )
        self.matches_scroll.config(command=self.matches_list.yview)

        self.matches_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.matches_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.matches_list.bind("<<ListboxSelect>>", self.on_match_selected)

        # Right: details (stacked sections)
        right = tk.Frame(mid)
        mid.add(right)

        # Parsed log
        parsed_lbl = tk.Label(right, text="Parsed Log")
        parsed_lbl.pack(side=tk.TOP, anchor="w")

        self.parsed_text = tk.Text(right, height=6, wrap=tk.WORD)
        self.parsed_text.pack(side=tk.TOP, fill=tk.X, expand=False, pady=(4, 8))
        self._set_text_readonly(self.parsed_text, "")

        # Matched line
        matched_lbl = tk.Label(right, text="Matched Line")
        matched_lbl.pack(side=tk.TOP, anchor="w")

        self.matched_text = tk.Text(right, height=3, wrap=tk.WORD)
        self.matched_text.pack(side=tk.TOP, fill=tk.X, expand=False, pady=(4, 8))
        self._set_text_readonly(self.matched_text, "")

        # Signature / context
        encl_lbl = tk.Label(right, text="Signature / Context")
        encl_lbl.pack(side=tk.TOP, anchor="w")

        encl_frame = tk.Frame(right)
        encl_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(4, 0))

        self.encl_scroll = tk.Scrollbar(encl_frame, orient=tk.VERTICAL)
        self.enclosing_text = tk.Text(
            encl_frame,
            wrap=tk.NONE,
            yscrollcommand=self.encl_scroll.set,
        )
        self.encl_scroll.config(command=self.enclosing_text.yview)

        # Monospace for code viewer
        try:
            self.enclosing_text.config(font=("Courier", 10))
        except Exception:
            pass

        self.enclosing_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.encl_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._set_text_readonly(self.enclosing_text, "")

        # -------- Bottom: status + settings summary --------
        bottom = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_var = tk.StringVar()
        self.status_label = tk.Label(bottom, textvariable=self.status_var, anchor="w")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)

        self.settings_var = tk.StringVar()
        self.settings_label = tk.Label(bottom, textvariable=self.settings_var, anchor="e")
        self.settings_label.pack(side=tk.RIGHT, padx=6, pady=4)
        self._refresh_settings_summary()

    def _refresh_settings_summary(self):
        roots = self._settings.get("roots", [])
        include_ext = self._settings.get("include_ext", [])
        exclude_dirs = self._settings.get("exclude_dirs", [])
        if self._demo_root:
            summary = "DEMO ROOT: %s" % (_safe_text(self._demo_root),)
        else:
            if roots:
                extra = ""
                if len(roots) > 1:
                    extra = " (+%d more)" % (len(roots) - 1,)
                root_summary = "%s%s" % (_safe_text(roots[0]), extra)
            else:
                root_summary = "(none)"
            summary = "Root: %s | Include: %s | Exclude dirs: %d" % (
                root_summary,
                ",".join(include_ext) if include_ext else "(none)",
                len(exclude_dirs),
            )
        self.settings_var.set(summary)

    def _refresh_banner(self):
        roots = self._settings.get("roots", []) if self._settings else []
        roots_text = ", ".join([_safe_text(r) for r in roots]) if roots else "(none)"
        if len(roots_text) > 120:
            roots_text = roots_text[:117] + "..."
        fw = "ON" if write_firewall.is_installed() else "OFF"
        self.banner_var.set(
            "Writable dir: %s | Firewall: %s | Scan roots: %s" % (_safe_text(self._data_dir), fw, roots_text)
        )

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
        return self.input_text.get("1.0", tk.END).strip("\n")

    def _set_text_readonly(self, widget, text):
        try:
            widget.config(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert("1.0", _safe_text(text))
            widget.config(state=tk.DISABLED)
        except Exception:
            # Last resort: don't crash the UI.
            pass

    def _render_parsed(self, parsed):
        if not self._result:
            self._set_text_readonly(self.parsed_text, "")
            return

        lines = []
        lines.append("Selected line:")
        lines.append(_safe_text(self._result.get("selected_line", "")))
        lines.append("")

        lines.append("Parsed:")
        for k in ("timestamp", "host_or_serial", "process", "level", "thread", "component", "message"):
            if parsed and (k in parsed):
                lines.append("%s: %s" % (k, _safe_text(parsed.get(k))))
        lines.append("")

        lines.append("Search:")
        lines.append("search_message: %s" % (_safe_text(self._result.get("search_message", "")),))

        scan_stats = (self._result or {}).get("scan_stats") or {}
        if scan_stats:
            lines.append("")
            lines.append("Scan stats:")
            for k in (
                "files_scanned",
                "files_skipped_excluded_dir",
                "files_skipped_symlink",
                "files_skipped_too_big",
                "files_skipped_unreadable",
                "hits_found",
                "elapsed_seconds",
                "stopped_reason",
            ):
                if k in scan_stats:
                    lines.append("%s: %s" % (k, _safe_text(scan_stats.get(k))))

        self._set_text_readonly(self.parsed_text, "\n".join(lines))

    def _render_selected_match(self):
        match = self._get_selected_match()
        if not match:
            self._set_text_readonly(self.matched_text, "")
            self._set_text_readonly(self.enclosing_text, "")
            return
        self._set_text_readonly(self.matched_text, match.get("line_text", ""))
        sig = match.get("signature")
        if sig:
            self._set_text_readonly(self.enclosing_text, sig)
        else:
            self._set_text_readonly(self.enclosing_text, match.get("context_preview", ""))

    def _get_selected_match(self):
        if not self._result:
            return None
        matches = self._result.get("matches") or []
        if self._selected_index is None:
            return None
        if self._selected_index < 0 or self._selected_index >= len(matches):
            return None
        return matches[self._selected_index]

    def _select_match_index(self, idx):
        self._selected_index = idx
        try:
            self.matches_list.selection_clear(0, tk.END)
            self.matches_list.selection_set(idx)
            self.matches_list.activate(idx)
            self.matches_list.see(idx)
        except Exception:
            pass
        self._render_selected_match()

    def on_analyze(self):
        log_text = self._get_input()
        self._set_status("Scanning...")
        try:
            self.root.update_idletasks()
        except Exception:
            pass

        def progress_cb(stats):
            try:
                msg = "Scanning... %d files, %d hits, %.1fs" % (
                    int(stats.get("files_scanned", 0)),
                    int(stats.get("hits_found", 0)),
                    float(stats.get("elapsed_seconds", 0.0)),
                )
                stopped = stats.get("stopped_reason")
                if stopped:
                    msg += " (stopped: %s)" % (_safe_text(stopped),)
                self._set_status(msg)
                try:
                    self.root.update_idletasks()
                except Exception:
                    pass
            except Exception:
                pass

        try:
            result = analyzer.analyze(log_text, self._settings, progress_cb=progress_cb)
        except Exception as e:
            self._set_status("Idle")
            messagebox.showerror("Analyzer error", _safe_text(e))
            return

        self._result = result or {"parsed": {}, "matches": []}
        parsed = self._result.get("parsed") or {}
        matches = self._result.get("matches") or []

        # Populate left list
        try:
            self.matches_list.delete(0, tk.END)
            for m in matches:
                path = m.get("path", "?")
                line = m.get("line_no", "?")
                base = os.path.basename(_safe_text(path))
                sig = m.get("signature")
                if sig:
                    right = _safe_text(sig)
                else:
                    right = "<no def> (context)"
                row = "%s:%s  |  %s" % (_safe_text(base), _safe_text(line), right)
                self.matches_list.insert(tk.END, row)
        except Exception:
            pass

        self._render_parsed(parsed)

        if matches:
            self._select_match_index(0)
        else:
            self._selected_index = None
            self._render_selected_match()

        scan_stats = (self._result or {}).get("scan_stats") or {}
        stopped = scan_stats.get("stopped_reason")
        elapsed = scan_stats.get("elapsed_seconds")
        try:
            elapsed = float(elapsed) if elapsed is not None else None
        except Exception:
            elapsed = None
        if elapsed is None:
            msg = "Found %d matches" % (len(matches),)
        else:
            msg = "Found %d matches in %.1fs" % (len(matches), elapsed)
        if stopped:
            msg += " (stopped: %s)" % (_safe_text(stopped),)
        self._set_status(msg)

    def on_match_selected(self, event=None):
        if not self._result:
            return
        try:
            sel = self.matches_list.curselection()
            if not sel:
                return
            idx = int(sel[0])
        except Exception:
            return
        self._selected_index = idx
        self._render_selected_match()

    def on_clear(self):
        self._result = None
        self._selected_index = None
        try:
            self.input_text.delete("1.0", tk.END)
        except Exception:
            pass
        try:
            self.matches_list.delete(0, tk.END)
        except Exception:
            pass
        self._set_text_readonly(self.parsed_text, "")
        self._set_text_readonly(self.matched_text, "")
        self._set_text_readonly(self.enclosing_text, "")
        self._set_status("Idle")

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


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    root = tk.Tk()
    ArrowLogHelperApp(root)
    root.minsize(900, 600)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())


