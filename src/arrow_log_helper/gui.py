from __future__ import absolute_import

import sys

try:
    import Tkinter as tk  # Python 2
    import tkMessageBox as messagebox
except ImportError:  # pragma: no cover (py3 fallback)
    import tkinter as tk  # type: ignore
    from tkinter import messagebox  # type: ignore


try:
    # Reuse the repo's existing defaults module (stdlib-only, data-only).
    from log_explainer.config_defaults import (  # noqa: F401
        DEFAULT_EXCLUDE_DIRS,
        DEFAULT_INCLUDE_EXT,
        DEFAULT_ROOTS,
    )
except Exception:
    DEFAULT_ROOTS = []
    DEFAULT_INCLUDE_EXT = [".py"]
    DEFAULT_EXCLUDE_DIRS = []


from arrow_log_helper import analyzer_stub


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

        self._settings = {
            "roots": list(DEFAULT_ROOTS),
            "include_ext": list(DEFAULT_INCLUDE_EXT),
            "exclude_dirs": list(DEFAULT_EXCLUDE_DIRS),
            "max_results": 20,
        }

        self._result = None
        self._selected_index = None

        self._build_ui()
        self._set_status("Idle")

    def _build_ui(self):
        # -------- Top: input + buttons --------
        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

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

        # Enclosing function
        encl_lbl = tk.Label(right, text="Enclosing Function")
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
        summary = "Roots: %d | Include: %s | Exclude dirs: %d" % (
            len(roots),
            ",".join(include_ext) if include_ext else "(none)",
            len(exclude_dirs),
        )
        self.settings_var.set(summary)

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
        if not parsed:
            self._set_text_readonly(self.parsed_text, "")
            return
        lines = []
        for k in ("timestamp", "machine", "component", "message"):
            if k in parsed:
                lines.append("%s: %s" % (k, _safe_text(parsed.get(k))))
        self._set_text_readonly(self.parsed_text, "\n".join(lines))

    def _render_selected_match(self):
        match = self._get_selected_match()
        if not match:
            self._set_text_readonly(self.matched_text, "")
            self._set_text_readonly(self.enclosing_text, "")
            return
        self._set_text_readonly(self.matched_text, match.get("matched_line", ""))
        self._set_text_readonly(self.enclosing_text, match.get("block", ""))

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

        try:
            result = analyzer_stub.analyze(log_text, self._settings)
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
                score = m.get("score", 0.0)
                comp = m.get("component", "unknown")
                path = m.get("path", "?")
                line = m.get("line", "?")
                row = "[%.2f] %s - %s:%s" % (
                    float(score),
                    _safe_text(comp),
                    _safe_text(path),
                    _safe_text(line),
                )
                self.matches_list.insert(tk.END, row)
        except Exception:
            pass

        self._render_parsed(parsed)

        if matches:
            self._select_match_index(0)
        else:
            self._selected_index = None
            self._render_selected_match()

        self._set_status("Found %d matches" % (len(matches),))

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

        parsed = (self._result or {}).get("parsed") or {}
        if parsed:
            lines.append("Parsed Log")
            lines.append("----------")
            for k in ("timestamp", "machine", "component", "message"):
                if k in parsed:
                    lines.append("%s: %s" % (k, _safe_text(parsed.get(k))))
            lines.append("")

        match = self._get_selected_match()
        if match:
            lines.append("Selected Match")
            lines.append("--------------")
            lines.append("score: %s" % (_safe_text(match.get("score")),))
            lines.append("component: %s" % (_safe_text(match.get("component")),))
            lines.append("path: %s:%s" % (_safe_text(match.get("path")), _safe_text(match.get("line"))))
            lines.append("")
            lines.append("Matched Line")
            lines.append("------------")
            lines.append(_safe_text(match.get("matched_line", "")))
            lines.append("")
            lines.append("Enclosing Function")
            lines.append("------------------")
            lines.append(_safe_text(match.get("block", "")))
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


