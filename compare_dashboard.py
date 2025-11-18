import os
import sys
import json
import hashlib
import traceback
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

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

# Colors for transfer status-based tagging
TRANSFER_TAG_COLORS = {
    'transfer_success': '#4caf50',   # green
    'transfer_diffsize': '#2196f3',  # blue
    'transfer_diffmod': '#9c27b0',   # purple
    'transfer_other': '#f44336',     # red
}

class FileCompareDashboard(tk.Tk):
    def __init__(self, json_path=LOG_JSON_PATH):
        super().__init__()
        self.title('Copy Results Dashboard')
        self.geometry('1200x700')
        self.json_path = json_path
        self.records = []
        self.filtered_records = []
        # Common roots for subdir filters
        self._src_common_root = ''
        self._dest_common_root = ''
        # Maps from tree item iid -> full path for quick actions (leaf nodes)
        self._src_iid_to_path = {}
        self._dest_iid_to_path = {}
        self._current_src_idx = None
        self._selection_syncing = False
        # Temporarily disable synced selection to mitigate crashes
        self._sync_selection_enabled = False
        # Guard for scroll sync to avoid recursion
        self._scroll_syncing = False
        self.create_widgets()
        self.load_records()
        self.apply_filter()

    def create_widgets(self):
        # Top frame for controls
        control_frame = ttk.Frame(self)
        control_frame.pack(fill='x', padx=8, pady=6)

        ttk.Label(control_frame, text='Transfer status:').pack(side='left')
        self.status_var = tk.StringVar(value='All')
        # Filter by transfer categories rather than file copy status
        status_options = ['All', 'Success', 'Different size', 'Different modtime', 'Other']
        status_menu = ttk.Combobox(control_frame, textvariable=self.status_var, values=status_options, width=30)
        status_menu.pack(side='left', padx=(4,10))
        status_menu.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        # Subdir filters (Original and Destination)
        ttk.Label(control_frame, text='Original subdir:').pack(side='left')
        self.src_subdir_var = tk.StringVar(value='All')
        self.src_subdir_combo = ttk.Combobox(control_frame, textvariable=self.src_subdir_var, values=['All'], width=24)
        self.src_subdir_combo.pack(side='left', padx=(4,10))
        self.src_subdir_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())


        # New: Destination subdir filters for subject, session, modality in a separate frame below Transfer status
        self.filter_frame = ttk.Frame(self)
        self.filter_frame.pack(fill='x', padx=8, pady=(0, 6))

        ttk.Label(self.filter_frame, text='Subject:').pack(side='left')
        self.dest_subject_var = tk.StringVar(value='All')
        self.dest_subject_combo = ttk.Combobox(self.filter_frame, textvariable=self.dest_subject_var, values=['All'], width=12)
        self.dest_subject_combo.pack(side='left', padx=(4,4))
        self.dest_subject_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Label(self.filter_frame, text='Session:').pack(side='left')
        self.dest_session_var = tk.StringVar(value='All')
        self.dest_session_combo = ttk.Combobox(self.filter_frame, textvariable=self.dest_session_var, values=['All'], width=10)
        self.dest_session_combo.pack(side='left', padx=(4,4))
        self.dest_session_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Label(self.filter_frame, text='Modality:').pack(side='left')
        self.dest_modality_var = tk.StringVar(value='All')
        self.dest_modality_combo = ttk.Combobox(self.filter_frame, textvariable=self.dest_modality_var, values=['All'], width=12)
        self.dest_modality_combo.pack(side='left', padx=(4,4))
        self.dest_modality_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Button(control_frame, text='Reload', command=self.reload).pack(side='left', padx=(0,6))
        ttk.Button(control_frame, text='Select JSON...', command=self.select_json).pack(side='left', padx=(0,6))
        ttk.Button(control_frame, text='Compute Checksums', command=self.compute_checksums_selected).pack(side='left', padx=(0,6))

        # Split pane
        paned = ttk.PanedWindow(self, orient='horizontal')
        paned.pack(fill='both', expand=True)

        # Left: destination files (full list)
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        ttk.Label(left_frame, text='Destination Files').pack(anchor='w', padx=4, pady=2)

        # Add checkbox column for safe deletion
        self.dest_tree = ttk.Treeview(left_frame, columns=('delete',), selectmode='extended')
        self.dest_tree.heading('#0', text='Destination')
        self.dest_tree.heading('delete', text='Del?')
        self.dest_tree.column('#0', width=380, anchor='w')
        self.dest_tree.column('delete', width=40, anchor='center')
        self.dest_tree.pack(fill='both', expand=True, padx=4, pady=4)
        self.dest_tree.bind('<<TreeviewSelect>>', self.on_dest_select)
        self.dest_tree.bind('<Button-1>', self.on_dest_click)
        
        # Track which items are checked for deletion
        self._delete_checked = set()

        # Right: original files (full list)
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        ttk.Label(right_frame, text='Original Files').pack(anchor='w', padx=4, pady=2)

        # Allow multi-selection on originals side as well, with delete checkbox
        self.source_tree = ttk.Treeview(right_frame, columns=('delete',), selectmode='extended')
        self.source_tree.heading('#0', text='Original')
        self.source_tree.heading('delete', text='Del?')
        self.source_tree.column('#0', width=380, anchor='w')
        self.source_tree.column('delete', width=40, anchor='center')
        self.source_tree.pack(fill='both', expand=True, padx=4, pady=4)
        self.source_tree.bind('<<TreeviewSelect>>', self.on_src_select)
        self.source_tree.bind('<Button-1>', self.on_src_click)
        
        # Track which original items are checked for deletion
        self._delete_checked_src = set()

        # Sync scroll between the two trees (software sync without visible scrollbar)
        self.dest_tree.configure(yscrollcommand=lambda f, l: self._on_treeview_scroll('dest', f, l))
        self.source_tree.configure(yscrollcommand=lambda f, l: self._on_treeview_scroll('source', f, l))

        # Details frames split into Original and New files (swapped positions)
        details_container = ttk.Frame(self)
        details_container.pack(fill='both', expand=False, padx=8, pady=(0,8))

        detail_left = ttk.LabelFrame(details_container, text='New file details')
        detail_left.pack(side='left', fill='both', expand=True, padx=(0,4))
        self.detail_dest_text = tk.Text(detail_left, height=6, wrap='word')
        self.detail_dest_text.pack(fill='both', expand=True)

        detail_right = ttk.LabelFrame(details_container, text='Original details')
        detail_right.pack(side='left', fill='both', expand=True, padx=(4,0))
        self.detail_src_text = tk.Text(detail_right, height=6, wrap='word')
        self.detail_src_text.pack(fill='both', expand=True)

        # Action buttons at the bottom
        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', padx=8, pady=(6, 8))
        ttk.Button(button_frame, text='Open in Finder', command=self.open_selected_in_finder).pack(side='left', padx=(0,6))
        ttk.Button(button_frame, text='Delete Selected Safely', command=self.delete_selected).pack(side='left', padx=(0,6))

    def select_json(self):
        path = filedialog.askopenfilename(title='Select copy_results.json', filetypes=[('JSON files','*.json')])
        if path:
            self.json_path = path
            self.reload()

    def reload(self):
        self.load_records()
        self.apply_filter()

    def load_records(self):
        self.records = []
        if not os.path.exists(self.json_path):
            messagebox.showerror('Error', f'JSON file not found: {self.json_path}')
            return
        try:
            with open(self.json_path, 'r') as f:
                data = json.load(f)
            for entry in data:
                # Normalise destination: could be list or string
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
                    'status': entry.get('status') or entry.get('Transfer Status'),
                    'transfer_status': entry.get('Transfer Status'),
                    'timestamp': entry.get('timestamp'),
                    'copy_date': entry.get('Copy Date'),
                    'copy_time': entry.get('Copy Time')
                })
            # Update common roots and subdir options after loading
            self._update_common_roots_and_filters()
        except Exception as e:
            messagebox.showerror('Error', f'Failed to parse JSON: {e}')

    def apply_filter(self):
        status_filter = self.status_var.get()
        src_subdir = self.src_subdir_var.get() if hasattr(self, 'src_subdir_var') else 'All'
        # Get new subdir filter values
        subject_filter = self.dest_subject_var.get() if hasattr(self, 'dest_subject_var') else 'All'
        session_filter = self.dest_session_var.get() if hasattr(self, 'dest_session_var') else 'All'
        modality_filter = self.dest_modality_var.get() if hasattr(self, 'dest_modality_var') else 'All'

        def match_src_subdir(rec):
            if src_subdir in (None, '', 'All'):
                return True
            p = rec.get('original')
            if not p:
                return False
            seg = self._top_level_subdir(os.path.dirname(p), self._src_common_root)
            return seg == src_subdir

        def match_dest_subdir(rec):
            # If all filters are 'All', always match (show all files)
            if (
                (subject_filter in (None, '', 'All')) and
                (session_filter in (None, '', 'All')) and
                (modality_filter in (None, '', 'All'))
            ):
                return True
            dests = rec.get('destinations') or []
            for d in dests:
                subj, sess, mod = self._parse_dest_subdir_fields(d)
                subj_match = (subject_filter in (None, '', 'All')) or (subj == subject_filter)
                sess_match = (session_filter in (None, '', 'All')) or (sess == session_filter)
                mod_match = (modality_filter in (None, '', 'All')) or (mod == modality_filter)
                if subj_match and sess_match and mod_match:
                    return True
            return False

        def match_status(rec):
            if status_filter == 'All':
                return True
            return self._transfer_category(rec) == status_filter

        self.filtered_records = [r for r in self.records if match_status(r) and match_src_subdir(r) and match_dest_subdir(r)]
        self.refresh_trees()

    def _parse_dest_subdir_fields(self, dest_path):
        # Example: .../sub-0953/241101/hedscan/...
        # Returns (subject, session, modality) or (None, None, None)
        try:
            parts = dest_path.replace('\\', '/').split('/')
            subj = None
            sess = None
            mod = None
            for i, p in enumerate(parts):
                if p.startswith('sub-'):
                    subj = p
                    if i+1 < len(parts):
                        sess = parts[i+1]
                    if i+2 < len(parts):
                        mod = parts[i+2]
                    break
            return subj, sess, mod
        except Exception:
            return None, None, None

    def _transfer_category(self, rec):
        t = (rec.get('transfer_status') or '').lower()
        if 'success' in t:
            return 'Success'
        if 'different size' in t or 'size mismatch' in t:
            return 'Different size'
        if 'different modtime' in t or 'modtime' in t:
            return 'Different modtime'
        return 'Other'

    def refresh_trees(self):
        # Clear trees
        for tree in (self.source_tree, self.dest_tree):
            for item in tree.get_children():
                tree.delete(item)
        self._src_iid_to_path.clear()
        self._dest_iid_to_path.clear()
        self._current_src_idx = None
        # Clear delete checkboxes when refreshing
        if hasattr(self, '_delete_checked'):
            self._delete_checked.clear()
        if hasattr(self, '_delete_checked_src'):
            self._delete_checked_src.clear()

        # Build aligned rows per record: for each destination shown, add a matching row on the originals side
    # dest_subdir_var is obsolete; removed
        global_row = 0
        for idx, rec in enumerate(self.filtered_records):
            status_text = rec.get('status') or 'Unknown'
            transfer = (rec.get('transfer_status') or '').lower() if rec.get('transfer_status') else ''
            if 'success' in transfer:
                tag = 'transfer_success'
            elif 'different size' in transfer or 'size mismatch' in transfer:
                tag = 'transfer_diffsize'
            elif 'different modtime' in transfer or 'modtime' in transfer:
                tag = 'transfer_diffmod'
            else:
                tag = 'transfer_other'
            original_path = rec.get('original')
            if not (original_path and os.path.exists(original_path)):
                continue
            # Filter destinations to those that exist and pass subdir filter
            view_dests = []
            for d in (rec.get('destinations') or []):
                if not (d and os.path.exists(d)):
                    continue
                # dest_subdir filter removed; subject/session/modality filters are now used in apply_filter
                view_dests.append(d)
            if not view_dests:
                continue

            for d_i, dest in enumerate(view_dests):
                zebra = 'row_even' if (global_row % 2 == 0) else 'row_odd'
                # Left: destination row
                iid_dest = f'dest{idx}-{d_i}'
                self.dest_tree.insert('', 'end', iid=iid_dest, text=os.path.basename(dest),
                                      values=('',), tags=(tag, zebra))
                self._dest_iid_to_path[iid_dest] = dest

                # Right: original row for the first destination, filler for subsequent
                if d_i == 0:
                    iid_src = f'src{idx}'
                    self.source_tree.insert('', 'end', iid=iid_src, text=os.path.basename(original_path),
                                            values=('',), tags=(tag, zebra))
                    self._src_iid_to_path[iid_src] = original_path
                else:
                    iid_pad = f'src{idx}-pad{d_i}'
                    self.source_tree.insert('', 'end', iid=iid_pad, text='', values=('',), tags=('filler', zebra))

                global_row += 1

        # Configure tag colors (force blue) and zebra backgrounds
        for tg, col in TRANSFER_TAG_COLORS.items():
            self.source_tree.tag_configure(tg, foreground=col)
            self.dest_tree.tag_configure(tg, foreground=col)
        self.source_tree.tag_configure('row_even', background='#ffffff')
        self.source_tree.tag_configure('row_odd', background='#f7f7f7')
        self.dest_tree.tag_configure('row_even', background='#ffffff')
        self.dest_tree.tag_configure('row_odd', background='#f7f7f7')
        # Filler styling (muted text)
        self.source_tree.tag_configure('filler', foreground='#999999')

        # Clear details
        self.detail_src_text.delete('1.0', 'end')
        self.detail_dest_text.delete('1.0', 'end')

    def _on_treeview_scroll(self, who, first, last):
        # Keep both treeviews vertically aligned
        try:
            if self._scroll_syncing:
                return
            self._scroll_syncing = True
            # Move both views to the same position (use 'first' fraction)
            self.source_tree.yview_moveto(first)
            self.dest_tree.yview_moveto(first)
        finally:
            self._scroll_syncing = False

    def on_dest_click(self, event):
        # Handle checkbox clicks in the delete column
        try:
            region = self.dest_tree.identify_region(event.x, event.y)
            if region != "cell":
                return
            column = self.dest_tree.identify_column(event.x)
            if column == '#1':  # Delete checkbox column
                item = self.dest_tree.identify_row(event.y)
                if item:
                    if item in self._delete_checked:
                        self._delete_checked.remove(item)
                        self.dest_tree.set(item, 'delete', '')
                    else:
                        self._delete_checked.add(item)
                        self.dest_tree.set(item, 'delete', '✓')
        except Exception as e:
            traceback.print_exc()

    def on_src_click(self, event):
        # Handle checkbox clicks in the delete column for originals
        try:
            region = self.source_tree.identify_region(event.x, event.y)
            if region != "cell":
                return
            column = self.source_tree.identify_column(event.x)
            if column == '#1':  # Delete checkbox column
                item = self.source_tree.identify_row(event.y)
                if item and not item.endswith('-pad'):  # Skip filler rows
                    if item in self._delete_checked_src:
                        self._delete_checked_src.remove(item)
                        self.source_tree.set(item, 'delete', '')
                    else:
                        self._delete_checked_src.add(item)
                        self.source_tree.set(item, 'delete', '✓')
        except Exception as e:
            traceback.print_exc()

    def on_dest_select(self, event=None):
        try:
            if self._selection_syncing:
                return
            # Update new file details only; do not sync selection to the originals list
            selected = self.dest_tree.selection()
            self.detail_dest_text.delete('1.0', 'end')
            if not selected:
                return
            # Update new file details
            self.update_new_detail()
            # Do not clear original details; allow both sides to be visible
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror('Error', f'Selection failed: {e}')

    def on_src_select(self, event=None):
        try:
            if self._selection_syncing:
                return
            selected = self.source_tree.selection()
            if not selected:
                self._current_src_idx = None
                self.detail_src_text.delete('1.0', 'end')
                return
            # Build unique indices for selected originals (skip filler rows)
            indices = []
            for iid in selected:
                if not iid.startswith('src'):
                    continue
                if '-pad' in iid:
                    continue
                try:
                    idx = int(iid[3:])
                except Exception:
                    continue
                if 0 <= idx < len(self.filtered_records):
                    indices.append(idx)
            # Remove duplicates while preserving order
            seen = set()
            unique_indices = []
            for i in indices:
                if i not in seen:
                    unique_indices.append(i)
                    seen.add(i)
            if not unique_indices:
                self.detail_src_text.delete('1.0', 'end')
                return
            self._current_src_idx = unique_indices[-1]
            self.update_original_detail_multi(unique_indices)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror('Error', f'Selection failed: {e}')

    # Global Tk callback error handler to avoid hard crashes
    def report_callback_exception(self, exc, val, tb):
        try:
            traceback.print_exception(exc, val, tb)
            messagebox.showerror('Error', f"Unexpected error: {val}")
        except Exception:
            pass

    def populate_dest_tree_for_index(self, idx):
        # Clear dest tree
        for item in self.dest_tree.get_children():
            self.dest_tree.delete(item)
        self._dest_iid_to_path.clear()
        rec = self.filtered_records[idx]
        dests = rec.get('destinations') or []
        for d_i, dest in enumerate(dests):
            base = os.path.basename(dest)
            size_val = self._path_size(dest)
            zebra = 'row_even' if d_i % 2 == 0 else 'row_odd'
            iid = f'dest{idx}-{d_i}'
            self.dest_tree.insert('', 'end', iid=iid, text=base,
                                  values=(size_val, rec.get('status')),
                                  tags=(rec.get('status'), zebra))
            self._dest_iid_to_path[iid] = dest

    def update_original_detail(self, idx):
        try:
            self.detail_src_text.delete('1.0', 'end')
            if idx is None or idx < 0 or idx >= len(self.filtered_records):
                return
            rec = self.filtered_records[idx]
            details = (
                f"Original: {rec.get('original')}\n"
                f"Basename: {os.path.basename(rec.get('original') or '')}\n"
                f"Size: {self.human_size(rec.get('original_size'))}\n"
                f"Status: {rec.get('status') or 'Unknown'}\n"
                f"Transfer: {rec.get('transfer_status')}\n"
                f"Timestamp: {rec.get('timestamp')}\n"
                f"Copy Date/Time: {rec.get('copy_date')} {rec.get('copy_time')}\n"
            )
            self.detail_src_text.insert('end', details)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror('Error', f'Update original details failed: {e}')

    def update_original_detail_multi(self, indices):
        try:
            self.detail_src_text.delete('1.0', 'end')
            blocks = []
            for idx in indices:
                if idx is None or idx < 0 or idx >= len(self.filtered_records):
                    continue
                rec = self.filtered_records[idx]
                block = (
                    f"Original: {rec.get('original')}\n"
                    f"Basename: {os.path.basename(rec.get('original') or '')}\n"
                    f"Size: {self.human_size(rec.get('original_size'))}\n"
                    f"Status: {rec.get('status') or 'Unknown'}\n"
                    f"Transfer: {rec.get('transfer_status')}\n"
                    f"Timestamp: {rec.get('timestamp')}\n"
                    f"Copy Date/Time: {rec.get('copy_date')} {rec.get('copy_time')}\n"
                )
                blocks.append(block)
            if blocks:
                self.detail_src_text.insert('end', ('\n' + ('-'*40) + '\n').join(blocks))
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror('Error', f'Update original details failed: {e}')

    def update_new_detail(self, event=None):
        try:
            self.detail_dest_text.delete('1.0', 'end')
            selected = self.dest_tree.selection()
            if not selected:
                return
            lines = []
            for iid in selected:
                p = self._dest_iid_to_path.get(iid)
                if not p:
                    continue
                size = self._path_size(p)
                exists = os.path.exists(p)
                lines.append(f"Path: {p}\nBasename: {os.path.basename(p)}\nSize: {size}\nExists: {exists}\n")
            if lines:
                self.detail_dest_text.insert('end', '\n'.join(lines))
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror('Error', f'Update new details failed: {e}')

    # Removed hierarchical tree helpers

    def _path_size(self, path):
        try:
            return self.human_size(os.path.getsize(path)) if path and os.path.exists(path) else ''
        except Exception:
            return ''

    # Removed scroll syncing logic as we no longer use hierarchical trees

    # Removed expand/collapse syncing as we no longer have groups

    # Removed expand/collapse helpers

    # Removed selection sync; right side is populated per selected source

    # Replaced by update_original_detail and update_new_detail

    def human_size(self, n):
        try:
            n = int(n)
        except Exception:
            return str(n)
        units = ['B','KB','MB','GB','TB']
        i = 0
        while n >= 1024 and i < len(units)-1:
            n /= 1024.0
            i += 1
        return f"{n:.1f} {units[i]}"

    def compute_checksums_selected(self):
        # Prefer destination selection; else source selection
        results = []
        dest_sel = list(self.dest_tree.selection())
        if dest_sel:
            for iid in dest_sel:
                p = self._dest_iid_to_path.get(iid)
                if p and os.path.isfile(p):
                    results.append(f"Dest SHA256: {p} -> {self.sha256(p)}")
        else:
            src_sel = list(self.source_tree.selection())
            if not src_sel:
                messagebox.showinfo('Checksums', 'Select a source or destination row first.')
                return
            iid = src_sel[0]
            try:
                idx = int(iid[3:])
            except Exception:
                idx = None
            if idx is not None and 0 <= idx < len(self.filtered_records):
                rec = self.filtered_records[idx]
                if os.path.isfile(rec.get('original') or ''):
                    results.append(f"Source SHA256: {rec['original']} -> {self.sha256(rec['original'])}")
                for d in rec.get('destinations') or []:
                    if os.path.isfile(d):
                        results.append(f"Dest SHA256: {d} -> {self.sha256(d)}")
        if results:
            self.detail_dest_text.insert('end', '\n'.join(results) + '\n')
        else:
            self.detail_dest_text.insert('end', '(No regular files found for checksum)\n')

    def _update_common_roots_and_filters(self):
        # Compute common roots
        src_dirs = [os.path.dirname(r['original']) for r in self.records if r.get('original')]
        dest_dirs = []
        for r in self.records:
            for d in (r.get('destinations') or []):
                if d:
                    dest_dirs.append(os.path.dirname(d))
        try:
            self._src_common_root = os.path.commonpath(src_dirs) if src_dirs else ''
        except Exception:
            self._src_common_root = ''
        try:
            self._dest_common_root = os.path.commonpath(dest_dirs) if dest_dirs else ''
        except Exception:
            self._dest_common_root = ''

        # Build options for subject, session, modality from all destination paths
        subjects = set()
        sessions = set()
        modalities = set()
        for d in dest_dirs:
            subj, sess, mod = self._parse_dest_subdir_fields(d)
            if subj:
                subjects.add(subj)
            if sess:
                sessions.add(sess)
            if mod:
                modalities.add(mod)

        subj_values = ['All'] + sorted(subjects)
        sess_values = ['All'] + sorted(sessions)
        mod_values = ['All'] + sorted(modalities)

        cur_subj = self.dest_subject_var.get() if hasattr(self, 'dest_subject_var') else 'All'
        cur_sess = self.dest_session_var.get() if hasattr(self, 'dest_session_var') else 'All'
        cur_mod = self.dest_modality_var.get() if hasattr(self, 'dest_modality_var') else 'All'
        if hasattr(self, 'dest_subject_combo'):
            self.dest_subject_combo['values'] = subj_values
            if cur_subj not in subj_values:
                self.dest_subject_var.set('All')
        if hasattr(self, 'dest_session_combo'):
            self.dest_session_combo['values'] = sess_values
            if cur_sess not in sess_values:
                self.dest_session_var.set('All')
        if hasattr(self, 'dest_modality_combo'):
            self.dest_modality_combo['values'] = mod_values
            if cur_mod not in mod_values:
                self.dest_modality_var.set('All')

    def _top_level_subdir(self, path_dir, common_root):
        try:
            if not path_dir:
                return None
            if common_root:
                rel = os.path.relpath(path_dir, common_root)
                if rel == '.' or rel == os.curdir:
                    return '(root)'
                # Normalize separators and take first segment
                parts = [p for p in rel.replace('\\', '/').split('/') if p and p != '.']
                return parts[0] if parts else '(root)'
            else:
                # No common root; return first segment of absolute path
                parts = [p for p in path_dir.replace('\\', '/').split('/') if p and p != '.']
                return parts[0] if parts else None
        except Exception:
            return None

    def sha256(self, path, block_size=65536):
        h = hashlib.sha256()
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(block_size), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            return f'Error: {e}'

    def open_selected_in_finder(self):
        selected = list(self.dest_tree.selection()) or list(self.source_tree.selection())
        paths = []
        for item in selected:
            if item in self._dest_iid_to_path:
                paths.append(self._dest_iid_to_path[item])
            elif item in self._src_iid_to_path:
                paths.append(self._src_iid_to_path[item])
        # Open each path in Finder (macOS)
        for p in paths:
            if p and os.path.exists(p):
                os.system(f"open -R '{p}'")

    def ensure_trash(self):
        if not os.path.exists(TRASH_DIR):
            os.makedirs(TRASH_DIR, exist_ok=True)

    def delete_selected(self):
        # Only delete items that are explicitly checked (from either list)
        if not self._delete_checked and not self._delete_checked_src:
            messagebox.showinfo('Delete', 'No files checked for deletion. Click checkboxes in the "Del?" column.')
            return
        # Collect file paths for checked items from destinations
        to_delete = []
        for item in self._delete_checked:
            if item in self._dest_iid_to_path:
                p = self._dest_iid_to_path[item]
                if p and os.path.exists(p) and os.path.isfile(p):
                    to_delete.append(p)
        # Collect file paths for checked items from originals
        for item in self._delete_checked_src:
            if item in self._src_iid_to_path:
                p = self._src_iid_to_path[item]
                if p and os.path.exists(p) and os.path.isfile(p):
                    to_delete.append(p)
        if not to_delete:
            messagebox.showinfo('Delete', 'No regular files among checked items.')
            return
        if not messagebox.askyesno('Confirm Deletion', f'Move {len(to_delete)} file(s) to trash?'):
            return
        self.ensure_trash()
        errors = []
        for p in to_delete:
            try:
                base = os.path.basename(p)
                target = os.path.join(TRASH_DIR, base)
                # Avoid overwrite in trash by appending counter
                counter = 1
                while os.path.exists(target):
                    name, ext = os.path.splitext(base)
                    target = os.path.join(TRASH_DIR, f"{name}_{counter}{ext}")
                    counter += 1
                shutil.move(p, target)
            except Exception as e:
                errors.append(f'{p}: {e}')
        if errors:
            messagebox.showerror('Delete', 'Errors occurred:\n' + '\n'.join(errors))
        else:
            messagebox.showinfo('Delete', f'Moved {len(to_delete)} file(s) to trash folder.')
        # Clear checked items from both lists
        self._delete_checked.clear()
        self._delete_checked_src.clear()
        # Refresh lists and details to reflect missing files
        self.apply_filter()
        self.detail_dest_text.delete('1.0', 'end')

if __name__ == '__main__':
    app = FileCompareDashboard()
    try:
        app.mainloop()
    except Exception as e:
        traceback.print_exc()
        try:
            messagebox.showerror('Error', f'Unexpected error: {e}')
        except Exception:
            pass
        sys.exit(1)
