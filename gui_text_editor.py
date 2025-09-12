import argparse
import os
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, QVBoxLayout, 
                             QWidget, QMenuBar, QMenu, QAction, QFileDialog, 
                             QMessageBox, QInputDialog, QStatusBar, QDialog,
                             QDialogButtonBox, QLabel, QLineEdit, QHBoxLayout,
                             QCheckBox)
from PyQt5.QtCore import Qt, QFileSystemWatcher, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence, QTextCursor


class FindReplaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find and Replace")
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QVBoxLayout()
        
        # Find section
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Find:"))
        self.find_input = QLineEdit()
        find_layout.addWidget(self.find_input)
        layout.addLayout(find_layout)
        
        # Replace section
        replace_layout = QHBoxLayout()
        replace_layout.addWidget(QLabel("Replace:"))
        self.replace_input = QLineEdit()
        replace_layout.addWidget(self.replace_input)
        layout.addLayout(replace_layout)
        
        # Options
        self.case_sensitive = QCheckBox("Case sensitive")
        layout.addWidget(self.case_sensitive)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)


class TextEditor(QMainWindow):
    def __init__(self, file_path: str = None, *, tsv_auto_align: bool = True):
        super().__init__()
        self.setWindowTitle("GUI Text Editor")
        self.resize(1000, 700)
        
        self._file_path = None
        self._modified = False
        self._tsv_auto_align = tsv_auto_align
        
        # Create central widget and text editor
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Text editor
        self.text_edit = QTextEdit()
        self.text_edit.setFont(QFont("Fira Code", 12))
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # File watcher for external changes
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.fileChanged.connect(self._on_file_changed)
        
        # Build menu
        self._build_menu()
        
        # Load file if given
        if file_path:
            self._open_path(file_path)

    def _build_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)
        
        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        reload_action = QAction("Reload", self)
        reload_action.triggered.connect(self.reload_file)
        file_menu.addAction(reload_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.text_edit.undo)
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(self.text_edit.redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        cut_action = QAction("Cut", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(self.text_edit.cut)
        edit_menu.addAction(cut_action)
        
        copy_action = QAction("Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.text_edit.copy)
        edit_menu.addAction(copy_action)
        
        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self.text_edit.paste)
        edit_menu.addAction(paste_action)
        
        edit_menu.addSeparator()
        
        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(self.text_edit.selectAll)
        edit_menu.addAction(select_all_action)
        
        edit_menu.addSeparator()
        
        find_action = QAction("Find...", self)
        find_action.setShortcut(QKeySequence.Find)
        find_action.triggered.connect(self.find_text)
        edit_menu.addAction(find_action)
        
        replace_action = QAction("Replace...", self)
        replace_action.setShortcut(QKeySequence.Replace)
        replace_action.triggered.connect(self.replace_text)
        edit_menu.addAction(replace_action)
        
        edit_menu.addSeparator()
        
        goto_action = QAction("Go to Line...", self)
        goto_action.setShortcut(QKeySequence("Ctrl+G"))
        goto_action.triggered.connect(self.goto_line)
        edit_menu.addAction(goto_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        wrap_action = QAction("Toggle Word Wrap", self)
        wrap_action.setShortcut(QKeySequence("Ctrl+W"))
        wrap_action.setCheckable(True)
        wrap_action.triggered.connect(self.toggle_wrap)
        view_menu.addAction(wrap_action)
        
        align_action = QAction("Align TSV Columns", self)
        align_action.triggered.connect(self.align_tsv_columns)
        view_menu.addAction(align_action)
        
        self.tsv_auto_action = QAction("Auto-align TSV on open", self)
        self.tsv_auto_action.setCheckable(True)
        self.tsv_auto_action.setChecked(self._tsv_auto_align)
        self.tsv_auto_action.triggered.connect(self._toggle_tsv_auto)
        view_menu.addAction(self.tsv_auto_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def new_file(self):
        """Create a new file"""
        if self._check_unsaved():
            self.text_edit.clear()
            self._file_path = None
            self._modified = False
            self._update_title()

    def open_file(self):
        """Open a file"""
        if not self._check_unsaved():
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "All Files (*)"
        )
        
        if file_path:
            self._open_path(file_path)

    def save_file(self):
        """Save the current file"""
        if self._file_path:
            self._save_to_path(self._file_path)
        else:
            self.save_file_as()

    def save_file_as(self):
        """Save the current file with a new name"""
        initial_name = os.path.basename(self._file_path) if self._file_path else ""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            initial_name,
            "All Files (*)"
        )
        
        if file_path:
            self._save_to_path(file_path)

    def reload_file(self):
        """Reload the current file from disk"""
        if self._file_path and os.path.exists(self._file_path):
            reply = QMessageBox.question(
                self,
                "Reload File",
                "Are you sure you want to reload? Unsaved changes will be lost.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self._open_path(self._file_path)

    def find_text(self):
        """Find text in the document"""
        text, ok = QInputDialog.getText(self, "Find", "Find:")
        if ok and text:
            cursor = self.text_edit.textCursor()
            found = self.text_edit.find(text)
            if not found:
                QMessageBox.information(self, "Find", f"'{text}' not found.")

    def replace_text(self):
        """Replace text in the document"""
        dialog = FindReplaceDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            find_text = dialog.find_input.text()
            replace_text = dialog.replace_input.text()
            
            if find_text:
                content = self.text_edit.toPlainText()
                if dialog.case_sensitive.isChecked():
                    new_content = content.replace(find_text, replace_text)
                else:
                    # Case insensitive replace
                    import re
                    new_content = re.sub(re.escape(find_text), replace_text, content, flags=re.IGNORECASE)
                
                if new_content != content:
                    self.text_edit.setPlainText(new_content)
                    count = content.count(find_text) if dialog.case_sensitive.isChecked() else len(re.findall(re.escape(find_text), content, re.IGNORECASE))
                    QMessageBox.information(self, "Replace", f"Replaced {count} occurrences.")
                else:
                    QMessageBox.information(self, "Replace", f"'{find_text}' not found.")

    def goto_line(self):
        """Go to a specific line number"""
        line_num, ok = QInputDialog.getInt(
            self,
            "Go to Line",
            "Line number:",
            1,
            1,
            self.text_edit.document().blockCount()
        )
        
        if ok:
            cursor = QTextCursor(self.text_edit.document().findBlockByLineNumber(line_num - 1))
            self.text_edit.setTextCursor(cursor)

    def toggle_wrap(self):
        """Toggle word wrapping"""
        if self.text_edit.lineWrapMode() == QTextEdit.NoWrap:
            self.text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        else:
            self.text_edit.setLineWrapMode(QTextEdit.NoWrap)

    def align_tsv_columns(self):
        """Align TSV columns for better readability"""
        content = self.text_edit.toPlainText()
        if '\t' in content:
            lines = content.split('\n')
            # Calculate maximum width for each column
            rows = [line.split('\t') for line in lines if line.strip()]
            if not rows:
                return
                
            max_cols = max(len(row) for row in rows)
            col_widths = [0] * max_cols
            
            for row in rows:
                for i, cell in enumerate(row):
                    if i < max_cols:
                        col_widths[i] = max(col_widths[i], len(cell))
            
            # Rebuild content with aligned columns
            aligned_lines = []
            for line in lines:
                if '\t' in line:
                    cells = line.split('\t')
                    aligned_cells = []
                    for i, cell in enumerate(cells):
                        if i < len(col_widths) - 1:  # Don't pad the last column
                            aligned_cells.append(cell.ljust(col_widths[i]))
                        else:
                            aligned_cells.append(cell)
                    aligned_lines.append('\t'.join(aligned_cells))
                else:
                    aligned_lines.append(line)
            
            self.text_edit.setPlainText('\n'.join(aligned_lines))

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About",
            "Simple GUI Text Editor (PyQt5)\n\n"
            "Keyboard Shortcuts:\n"
            "  Ctrl+N - New\n"
            "  Ctrl+O - Open\n"
            "  Ctrl+S - Save\n"
            "  Ctrl+Shift+S - Save As\n"
            "  Ctrl+F - Find\n"
            "  Ctrl+H - Replace\n"
            "  Ctrl+G - Go to Line\n"
            "  Ctrl+W - Toggle Word Wrap\n"
            "  Ctrl+Q - Quit"
        )

    def _open_path(self, file_path):
        """Open a file from the given path"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.text_edit.setPlainText(content)
            self._file_path = file_path
            self._modified = False
            self._update_title()
            
            # Add to file watcher
            if self.file_watcher.files():
                self.file_watcher.removePaths(self.file_watcher.files())
            self.file_watcher.addPath(file_path)
            
            # Auto-align TSV if enabled
            if self._tsv_auto_align and file_path.endswith('.tsv'):
                self.align_tsv_columns()
                
        except Exception as e:
            QMessageBox.critical(self, "Open Error", f"Couldn't open file:\n{e}")

    def _save_to_path(self, file_path):
        """Save content to the given path"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.text_edit.toPlainText())
            
            self._file_path = file_path
            self._modified = False
            self._update_title()
            
            # Update file watcher
            if self.file_watcher.files():
                self.file_watcher.removePaths(self.file_watcher.files())
            self.file_watcher.addPath(file_path)
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Couldn't save file:\n{e}")

    def _check_unsaved(self):
        """Check if there are unsaved changes and ask user what to do"""
        if not self._modified:
            return True
            
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The document has been modified. Do you want to save your changes?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save
        )
        
        if reply == QMessageBox.Save:
            self.save_file()
            return not self._modified  # Only continue if save was successful
        elif reply == QMessageBox.Discard:
            return True
        else:  # Cancel
            return False

    def _on_text_changed(self):
        """Handle text changes"""
        self._modified = True
        self._update_title()

    def _on_file_changed(self, path):
        """Handle external file changes"""
        if path == self._file_path:
            reply = QMessageBox.question(
                self,
                "File Changed",
                "The file has been modified by another program. Do you want to reload it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self._open_path(path)

    def _update_title(self):
        """Update the window title"""
        title = "GUI Text Editor"
        if self._file_path:
            title += f" - {os.path.basename(self._file_path)}"
        if self._modified:
            title += " *"
        self.setWindowTitle(title)

    def _toggle_tsv_auto(self):
        """Toggle TSV auto-alignment"""
        self._tsv_auto_align = self.tsv_auto_action.isChecked()

    def closeEvent(self, event):
        """Handle window close event"""
        if self._check_unsaved():
            event.accept()
        else:
            event.ignore()


def main():
    parser = argparse.ArgumentParser(description="Simple GUI Text Editor")
    parser.add_argument("file", nargs="?", help="File to open")
    parser.add_argument("--no-tsv-align", action="store_true", 
                       help="Disable automatic TSV column alignment")
    
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    editor = TextEditor(
        file_path=args.file,
        tsv_auto_align=not args.no_tsv_align
    )
    editor.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
