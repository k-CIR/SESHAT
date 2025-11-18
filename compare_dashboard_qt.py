import os
import sys
import json
import hashlib
import shutil
from typing import List, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QFileDialog, QMessageBox, QTextEdit, QComboBox, QSizePolicy
)
from PyQt6.QtCore import Qt

LOG_JSON_PATH = os.path.join('neuro', 'data', 'local', 'OPM-benchmarking', 'logs', 'copy_results.json')
TRASH_DIR = os.path.join('neuro', 'data', 'local', 'OPM-benchmarking', '.trash')

STATUS_COLORS = {
    'Copied': '#4caf50',
    'File already up to date': '#2196f3',
    'Copied (split if > 2GB)': '#9c27b0',
    'Error': '#f44336',
    'Missing': '#ff9800',
    'Unknown': '#666666'
}

class CompareDashboardQt(QWidget):
    def __init__(self, json_path: str = LOG_JSON_PATH):
        super().__init__()
        self.setWindowTitle('Copy Results Dashboard (Qt)')
        self.resize(1200, 700)
        self.json_path = json_path
        self.records: List[Dict[str, Any]] = []
        self.filtered_records: List[Dict[str, Any]] = []
        self._src_common_root = ''
        self._dest_common_root = ''
        self._current_src_idx = None

        self._build_ui()
        self.load_records()
        self.apply_filters()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        controls = QHBoxLayout()
        outer.addLayout(controls)

        controls.addWidget(QLabel('Status:'))
        self.status_combo = QComboBox()
        self.status_combo.addItems(['All','Copied','File already up to date','Copied (split if > 2GB)','Error','Missing'])
        self.status_combo.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.status_combo)

        controls.addWidget(QLabel('Original subdir:'))
        self.src_subdir_combo = QComboBox(); self.src_subdir_combo.addItem('All')
        self.src_subdir_combo.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.src_subdir_combo)

        controls.addWidget(QLabel('Dest subdir:'))
        self.dest_subdir_combo = QComboBox(); self.dest_subdir_combo.addItem('All')
        self.dest_subdir_combo.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.dest_subdir_combo)

        btn_reload = QPushButton('Reload'); btn_reload.clicked.connect(self.reload); controls.addWidget(btn_reload)
        btn_select = QPushButton('Select JSON...'); btn_select.clicked.connect(self.select_json); controls.addWidget(btn_select)
        btn_checksum = QPushButton('Compute Checksums'); btn_checksum.clicked.connect(self.compute_checksums); controls.addWidget(btn_checksum)
        btn_open = QPushButton('Open in Finder'); btn_open.clicked.connect(self.open_in_finder); controls.addWidget(btn_open)
        btn_delete = QPushButton('Delete Selected'); btn_delete.clicked.connect(self.delete_selected); controls.addWidget(btn_delete)
        controls.addStretch(1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        # Left: destinations
        left_widget = QWidget(); left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel('Destination Files'))
        self.dest_list = QListWidget(); self.dest_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.dest_list.itemSelectionChanged.connect(self.on_dest_selection)
        left_layout.addWidget(self.dest_list, 1)
        splitter.addWidget(left_widget)

        # Right: originals
        right_widget = QWidget(); right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel('Original Files'))
        self.src_list = QListWidget(); self.src_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.src_list.itemSelectionChanged.connect(self.on_src_selection)
        right_layout.addWidget(self.src_list, 1)
        splitter.addWidget(right_widget)

        # Details
        details_row = QHBoxLayout(); outer.addLayout(details_row)
        self.src_detail = QTextEdit(); self.src_detail.setReadOnly(True); self.src_detail.setMinimumHeight(140)
        self.dest_detail = QTextEdit(); self.dest_detail.setReadOnly(True); self.dest_detail.setMinimumHeight(140)
        details_row.addWidget(self.src_detail, 1)
        details_row.addWidget(self.dest_detail, 1)

    def select_json(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select copy_results.json', '', 'JSON Files (*.json)')
        if path:
            self.json_path = path
            self.reload()

    def reload(self):
        self.load_records()
        self.apply_filters()

    def load_records(self):
        self.records.clear()
        if not os.path.exists(self.json_path):
            QMessageBox.critical(self, 'Error', f'JSON not found: {self.json_path}')
            return
        try:
            with open(self.json_path, 'r') as f:
                data = json.load(f)
            for entry in data:
                dest = entry.get('New file(s)')
                if isinstance(dest, list):
                    dest_list = dest
                else:
                    dest_list = [dest] if dest else []
                self.records.append({
                    'original': entry.get('Original File'),
                    'destinations': dest_list,
                    'original_size': entry.get('Original Size', 0),
                    'destination_size': entry.get('Total Destination Size', 0),
                    'status': entry.get('status') or entry.get('Transfer Status') or 'Unknown',
                    'transfer_status': entry.get('Transfer Status'),
                    'timestamp': entry.get('timestamp'),
                    'copy_date': entry.get('Copy Date'),
                    'copy_time': entry.get('Copy Time')
                })
            self._update_subdir_filters()
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to parse JSON: {e}')

    def _common_root(self, paths: List[str]) -> str:
        try:
            return os.path.commonpath(paths) if paths else ''
        except Exception:
            return ''

    def _top_segment(self, path_dir: str, common_root: str) -> str | None:
        try:
            if not path_dir:
                return None
            if common_root:
                rel = os.path.relpath(path_dir, common_root)
                if rel == '.':
                    return '(root)'
                parts = [p for p in rel.replace('\\','/').split('/') if p and p != '.']
                return parts[0] if parts else '(root)'
            parts = [p for p in path_dir.replace('\\','/').split('/') if p and p != '.']
            return parts[0] if parts else None
        except Exception:
            return None

    def _update_subdir_filters(self):
        src_dirs = [os.path.dirname(r['original']) for r in self.records if r.get('original')]
        dest_dirs = []
        for r in self.records:
            for d in r.get('destinations') or []:
                if d:
                    dest_dirs.append(os.path.dirname(d))
        self._src_common_root = self._common_root(src_dirs)
        self._dest_common_root = self._common_root(dest_dirs)
        src_opts = sorted({seg for seg in (self._top_segment(d, self._src_common_root) for d in src_dirs) if seg})
        dest_opts = sorted({seg for seg in (self._top_segment(d, self._dest_common_root) for d in dest_dirs) if seg})

        def repop(combo: QComboBox, opts: List[str]):
            cur = combo.currentText() if combo.count() else 'All'
            combo.clear(); combo.addItem('All')
            for o in opts:
                combo.addItem(o)
            if cur in ['All'] + opts:
                combo.setCurrentText(cur)
            else:
                combo.setCurrentText('All')

        repop(self.src_subdir_combo, src_opts)
        repop(self.dest_subdir_combo, dest_opts)

    def apply_filters(self):
        status_filter = self.status_combo.currentText()
        src_subdir = self.src_subdir_combo.currentText()
        dest_subdir = self.dest_subdir_combo.currentText()

        def match_status(r):
            return status_filter == 'All' or r.get('status') == status_filter
        def match_src(r):
            if src_subdir in ('All',''):
                return True
            p = r.get('original')
            return self._top_segment(os.path.dirname(p), self._src_common_root) == src_subdir if p else False
        def match_dest(r):
            if dest_subdir in ('All',''):
                return True
            for d in r.get('destinations') or []:
                if self._top_segment(os.path.dirname(d), self._dest_common_root) == dest_subdir:
                    return True
            return False

        self.filtered_records = [r for r in self.records if match_status(r) and match_src(r) and match_dest(r)]
        self.refresh_lists()

    def refresh_lists(self):
        self.src_list.clear(); self.dest_list.clear()
        # Originals (right)
        for idx, r in enumerate(self.filtered_records):
            base = os.path.basename(r.get('original') or '') or '(missing)'
            item = QListWidgetItem(base)
            item.setData(Qt.ItemDataRole.UserRole, ('src', idx))
            item.setToolTip(r.get('original') or '')
            self.src_list.addItem(item)
        # Destinations (left)
        for idx, r in enumerate(self.filtered_records):
            for d_i, dest in enumerate(r.get('destinations') or []):
                base = os.path.basename(dest)
                di = QListWidgetItem(base)
                di.setData(Qt.ItemDataRole.UserRole, ('dest', idx, d_i))
                di.setToolTip(dest)
                self.dest_list.addItem(di)
        self.src_detail.clear(); self.dest_detail.clear()

    def on_dest_selection(self):
        self.dest_detail.clear()
        items = self.dest_list.selectedItems()
        if not items:
            return
        lines = []
        first_src_idx = None
        for it in items:
            meta = it.data(Qt.ItemDataRole.UserRole)
            if not meta or meta[0] != 'dest':
                continue
            _, src_idx, d_i = meta
            rec = self.filtered_records[src_idx]
            dest_path = rec.get('destinations')[d_i]
            size = self._size(dest_path)
            lines.append(f"Path: {dest_path}\nBasename: {os.path.basename(dest_path)}\nSize: {size}\nExists: {os.path.exists(dest_path)}\n")
            if first_src_idx is None:
                first_src_idx = src_idx
        self.dest_detail.setPlainText('\n'.join(lines))
        # Sync original selection
        if first_src_idx is not None and first_src_idx < self.src_list.count():
            self.src_list.setCurrentRow(first_src_idx)
            self.update_src_detail(first_src_idx)

    def on_src_selection(self):
        items = self.src_list.selectedItems()
        self.src_detail.clear()
        if not items:
            return
        meta = items[0].data(Qt.ItemDataRole.UserRole)
        if not meta or meta[0] != 'src':
            return
        _, idx = meta
        self.update_src_detail(idx)

    def update_src_detail(self, idx: int):
        if idx < 0 or idx >= len(self.filtered_records):
            return
        r = self.filtered_records[idx]
        details = (
            f"Original: {r.get('original')}\n"
            f"Basename: {os.path.basename(r.get('original') or '')}\n"
            f"Size: {self._size(r.get('original'))}\n"
            f"Status: {r.get('status')}\n"
            f"Transfer: {r.get('transfer_status')}\n"
            f"Timestamp: {r.get('timestamp')}\n"
            f"Copy Date/Time: {r.get('copy_date')} {r.get('copy_time')}\n"
            f"Destinations: {len(r.get('destinations') or [])}\n"
        )
        self.src_detail.setPlainText(details)

    def _size(self, path: str | None) -> str:
        try:
            if path and os.path.exists(path):
                n = os.path.getsize(path)
                units = ['B','KB','MB','GB','TB']
                i = 0
                while n >= 1024 and i < len(units)-1:
                    n /= 1024.0
                    i += 1
                return f"{n:.1f} {units[i]}"
            return ''
        except Exception:
            return ''

    def compute_checksums(self):
        items = self.dest_list.selectedItems() or self.src_list.selectedItems()
        if not items:
            QMessageBox.information(self, 'Checksums', 'Select destination(s) or an original first.')
            return
        lines = []
        for it in items:
            meta = it.data(Qt.ItemDataRole.UserRole)
            if not meta:
                continue
            if meta[0] == 'dest':
                _, src_idx, d_i = meta
                rec = self.filtered_records[src_idx]
                path = rec.get('destinations')[d_i]
            elif meta[0] == 'src':
                _, src_idx = meta
                rec = self.filtered_records[src_idx]
                path = rec.get('original')
            else:
                continue
            if path and os.path.isfile(path):
                lines.append(f"SHA256 {path}: {self._sha256(path)}")
        if lines:
            self.dest_detail.append('\n'.join(lines))
        else:
            self.dest_detail.append('(No regular files found for checksum)')

    def _sha256(self, path: str, block: int = 65536) -> str:
        h = hashlib.sha256()
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(block), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            return f'Error: {e}'

    def open_in_finder(self):
        items = self.dest_list.selectedItems() or self.src_list.selectedItems()
        paths = []
        for it in items:
            meta = it.data(Qt.ItemDataRole.UserRole)
            if not meta:
                continue
            if meta[0] == 'dest':
                _, src_idx, d_i = meta
                rec = self.filtered_records[src_idx]
                paths.append(rec.get('destinations')[d_i])
            elif meta[0] == 'src':
                _, src_idx = meta
                rec = self.filtered_records[src_idx]
                p = rec.get('original')
                if p:
                    paths.append(p)
        for p in paths:
            if p and os.path.exists(p):
                os.system(f"open -R '{p}'")

    def ensure_trash(self):
        if not os.path.exists(TRASH_DIR):
            os.makedirs(TRASH_DIR, exist_ok=True)

    def delete_selected(self):
        items = self.dest_list.selectedItems()
        if not items:
            QMessageBox.information(self, 'Delete', 'Select destination items to delete.')
            return
        paths = []
        for it in items:
            meta = it.data(Qt.ItemDataRole.UserRole)
            if meta and meta[0] == 'dest':
                _, src_idx, d_i = meta
                rec = self.filtered_records[src_idx]
                p = rec.get('destinations')[d_i]
                if p and os.path.isfile(p):
                    paths.append(p)
        if not paths:
            QMessageBox.information(self, 'Delete', 'No regular files among selected destinations.')
            return
        if QMessageBox.question(self, 'Confirm', f'Move {len(paths)} file(s) to trash?') != QMessageBox.StandardButton.Yes:
            return
        self.ensure_trash()
        errors = []
        for p in paths:
            try:
                base = os.path.basename(p)
                target = os.path.join(TRASH_DIR, base)
                counter = 1
                while os.path.exists(target):
                    name, ext = os.path.splitext(base)
                    target = os.path.join(TRASH_DIR, f"{name}_{counter}{ext}")
                    counter += 1
                shutil.move(p, target)
            except Exception as e:
                errors.append(f'{p}: {e}')
        if errors:
            QMessageBox.critical(self, 'Delete', 'Errors:\n' + '\n'.join(errors))
        else:
            QMessageBox.information(self, 'Delete', f'Moved {len(paths)} file(s) to trash.')
        self.apply_filters()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = CompareDashboardQt()
    w.show()
    sys.exit(app.exec())
