import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from tkinter import font as tkfont


class TextEditor(tk.Tk):
    def __init__(self, file_path: str | None = None, *, tsv_auto_align: bool = True):
        super().__init__()
        self.title("GUI Text Editor")
        self.geometry("1000x700")
        self._file_path: str | None = None
        self._modified = False
        self._wrap = tk.NONE
        self._tsv_auto_align = tsv_auto_align
        self._font = tkfont.Font(font=("Fira Code", 12))

        # Build UI
        self._build_menu()
        self._build_editor()
        self._build_statusbar()

        # Key bindings
        self.bind_all("<Control-s>", lambda e: self.save_file())
        self.bind_all("<Control-S>", lambda e: self.save_file_as())
        self.bind_all("<Control-o>", lambda e: self.open_file())
        self.bind_all("<Control-f>", lambda e: self.find_text())
        self.bind_all("<Control-h>", lambda e: self.replace_text())
        self.bind_all("<Control-g>", lambda e: self.goto_line())
        self.bind_all("<Control-q>", lambda e: self.on_exit())

        # Load file if given
        if file_path:
            self._open_path(file_path)

        # Protocol for window close
        self.protocol("WM_DELETE_WINDOW", self.on_exit)

    # UI builders
    def _build_menu(self):
        menubar = tk.Menu(self)
        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        self.bind_all("<Control-n>", lambda e: self.new_file())
        file_menu.add_command(label="Open…", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As…", command=self.save_file_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Reload", command=self.reload_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_exit, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo", command=lambda: self.text.event_generate("<<Undo>>"), accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=lambda: self.text.event_generate("<<Redo>>"), accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut", command=lambda: self.text.event_generate("<<Cut>>"), accelerator="Ctrl+X")
        edit_menu.add_command(label="Copy", command=lambda: self.text.event_generate("<<Copy>>"), accelerator="Ctrl+C")
        edit_menu.add_command(label="Paste", command=lambda: self.text.event_generate("<<Paste>>"), accelerator="Ctrl+V")
        edit_menu.add_separator()
        edit_menu.add_command(label="Find…", command=self.find_text, accelerator="Ctrl+F")
        edit_menu.add_command(label="Replace…", command=self.replace_text, accelerator="Ctrl+H")
        edit_menu.add_command(label="Go to line…", command=self.goto_line, accelerator="Ctrl+G")
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", command=lambda: self.text.tag_add("sel", "1.0", "end"), accelerator="Ctrl+A")
        self.bind_all("<Control-a>", lambda e: (self.text.tag_add("sel", "1.0", "end"), "break"))
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # View
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Wrap", command=self.toggle_wrap)
        view_menu.add_command(label="Align TSV Columns", command=self.align_tsv_columns)
        self._tsv_var = tk.BooleanVar(value=self._tsv_auto_align)
        view_menu.add_checkbutton(label="Auto-align TSV on open", variable=self._tsv_var, command=self._toggle_tsv_auto)
        menubar.add_cascade(label="View", menu=view_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo(
            "About",
            "Simple GUI Text Editor\n\nKeys:\n  Ctrl+O Open\n  Ctrl+S Save\n  Ctrl+Shift+S Save As\n  Ctrl+F Find\n  Ctrl+H Replace\n  Ctrl+G Go to line\n  Ctrl+Q Quit",
        ))
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _build_editor(self):
        self.text = ScrolledText(self, undo=True, wrap=self._wrap, font=("Fira Code", 12))
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<KeyRelease>", self._update_status)
        self.text.bind("<ButtonRelease>", self._update_status)

    def _build_statusbar(self):
        self.status = tk.StringVar(value="Ready")
        bar = tk.Label(self, textvariable=self.status, anchor="w", relief=tk.SUNKEN)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

    # File ops
    def new_file(self):
        if not self._confirm_discard_changes():
            return
        self.text.delete("1.0", tk.END)
        self._file_path = None
        self._set_title()
        self._set_modified(False)

    def open_file(self):
        if not self._confirm_discard_changes():
            return
        path = filedialog.askopenfilename()
        if path:
            self._open_path(path)

    def _open_path(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Open error", f"Couldn't open file:\n{e}")
            return
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self._file_path = path
        self._set_title()
        self._set_modified(False)
        self._update_status()
        # Auto-align TSV files on open if enabled
        if self._tsv_var.get() and (os.path.splitext(path)[1].lower() == ".tsv" or "\t" in content):
            self.align_tsv_columns()

    def save_file(self):
        if self._file_path is None:
            return self.save_file_as()
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                f.write(self.text.get("1.0", tk.END))
            self._set_modified(False)
            self._update_status("Saved")
        except Exception as e:
            messagebox.showerror("Save error", f"Couldn't save file:\n{e}")

    def save_file_as(self):
        path = filedialog.asksaveasfilename(initialfile=os.path.basename(self._file_path) if self._file_path else None)
        if not path:
            return
        self._file_path = path
        self._set_title()
        self.save_file()

    def reload_file(self):
        if not self._file_path:
            return
        if not self._confirm_discard_changes():
            return
        self._open_path(self._file_path)

    # Edit ops
    def find_text(self):
        term = simpledialog.askstring("Find", "Find:")
        if not term:
            return
        self.text.tag_remove("find", "1.0", tk.END)
        start = "1.0"
        count = 0
        while True:
            pos = self.text.search(term, start, stopindex=tk.END, nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(term)}c"
            self.text.tag_add("find", pos, end)
            self.text.tag_config("find", background="#ffeaa7")
            start = end
            count += 1
        if count:
            self.text.see(pos)
        self._update_status(f"Found {count} matches")

    def replace_text(self):
        term = simpledialog.askstring("Replace", "Find:")
        if term is None:
            return
        repl = simpledialog.askstring("Replace", "Replace with:")
        if repl is None:
            return
        content = self.text.get("1.0", tk.END)
        new_content = content.replace(term, repl)
        if new_content != content:
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", new_content)
            self._set_modified(True)
        self._update_status("Replaced")

    def goto_line(self):
        try:
            line = simpledialog.askinteger("Go to line", "Line number:", minvalue=1)
            if line:
                self.text.mark_set("insert", f"{line}.0")
                self.text.see("insert")
                self._update_status()
        except Exception:
            pass

    def toggle_wrap(self):
        self._wrap = tk.WORD if self._wrap == tk.NONE else tk.NONE
        self.text.config(wrap=self._wrap)

    def _toggle_tsv_auto(self):
        self._tsv_auto_align = self._tsv_var.get()

    def align_tsv_columns(self):
        # Determine columns widths in pixels and set tab stops accordingly
        content = self.text.get("1.0", tk.END)
        lines = content.splitlines()
        if not lines:
            return
        # Limit for performance
        sample = lines[:2000]
        cols_max_px: list[int] = []
        for line in sample:
            parts = line.split("\t")
            # Extend cols_max_px
            if len(parts) > len(cols_max_px):
                cols_max_px.extend([0] * (len(parts) - len(cols_max_px)))
            for i, cell in enumerate(parts):
                width = self._font.measure(cell if cell is not None else "")
                # Add padding 24px
                if width + 24 > cols_max_px[i]:
                    cols_max_px[i] = width + 24
        if not cols_max_px:
            return
        # Build cumulative tab stops
        tabs: list[int] = []
        cum = 0
        for w in cols_max_px:
            cum += max(w, 48)
            tabs.append(cum)
        self.text.config(tabs=tuple(tabs))
        self._update_status("TSV columns aligned")

    # Helpers
    def _set_title(self):
        name = self._file_path if self._file_path else "Untitled"
        mod = "*" if self._modified else ""
        self.title(f"{os.path.basename(name)}{mod} - GUI Text Editor")

    def _set_modified(self, value: bool):
        self._modified = value
        self.text.edit_modified(0)
        self._set_title()

    def _on_modified(self, _):
        self._modified = True
        self._set_title()
        self.text.edit_modified(0)
        self._update_status()

    def _update_status(self, msg: str | None = None):
        if msg:
            self.status.set(msg)
            return
        idx = self.text.index(tk.INSERT).split(".")
        line, col = int(idx[0]), int(idx[1])
        path = self._file_path or "Untitled"
        self.status.set(f"{path}   Ln {line}, Col {col}")

    def _confirm_discard_changes(self) -> bool:
        if not self._modified:
            return True
        ans = messagebox.askyesnocancel("Unsaved changes", "You have unsaved changes. Save before proceeding?")
        if ans is None:
            return False
        if ans:
            self.save_file()
            return not self._modified
        return True

    def on_exit(self):
        if not self._confirm_discard_changes():
            return
        self.destroy()


def launch_editor(file_path: str | None = None, *, tsv_auto_align: bool = True):
    app = TextEditor(file_path=file_path, tsv_auto_align=tsv_auto_align)
    app.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Simple GUI Text Editor")
    parser.add_argument("file", nargs="?", default=None, help="File to open (positional)")
    parser.add_argument("-o", "--open", dest="open_file", default=None, help="Path to file to open")
    parser.add_argument("--no-tsv-align", action="store_true", help="Disable auto TSV column alignment on open")
    args = parser.parse_args()
    path = args.open_file or args.file
    launch_editor(path, tsv_auto_align=not args.no_tsv_align)


if __name__ == "__main__":
    main()
