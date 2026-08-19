import yaml
import json
import sys
import os
import argparse
import re
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from seshat.utils import apply_ansi_colors_to_tk

default_path = '/neuro/data/local'

# Human-readable labels for snake_case RUN keys
RUN_LABELS = {
    'copy_raw':       'Copy raw data',
    'opm_preprocess': 'OPM preprocessing',
    'sync':           'Sync to server',
}


def create_default_config():
    """Create default configuration dictionary without GUI dependencies"""
    config = {
        'RUN': {
            'copy_raw':       True,
            'opm_preprocess': True,
            'sync':           True
        },
        'Project': {
            'Name': '',
            'cir_id': '',
            'InstitutionName': 'Karolinska Institutet',
            'InstitutionAddress': 'Nobels vag 9, 171 77, Stockholm, Sweden',
            'InstitutionDepartmentName': 'Department of Clinical Neuroscience (CNS)',
            'Description': 'project for MEG data',
            'Tasks': [''],
            'sinuhe_raw': '/neuro/data/sinuhe/<project_path_on_sinuhe>',
            'kaptah_raw': '/neuro/data/kaptah/<project_path_on_kaptah>',
            'stimulus':   '/neuro/data/stimulus/<project_path_on_stimulus>',
            'Polhemus':   '/neuro/data/polhemus/<project>',
            'Root': default_path,
            'Raw':  f'{default_path}/<project>/raw',
            'BIDS': f'{default_path}/<project>/BIDS',
            'Calibration': f'{default_path}/<project>/triux_files/sss/sss_cal.dat',
            'Crosstalk':   f'{default_path}/<project>/triux_files/ctc/ct_sparse.fif',
            'logfile': 'pipeline_log.log'
        },
        'OPM': {
            'rename_analog_channels': True,
            'polhemus': [''],
            'hpi_names': ['HPIpre', 'HPIpost', 'HPIbefore', 'HPIafter'],
            'frequency': 33,
            'downsample_to_hz': 1000,
            'overwrite': False,
            'plot': False,
        },
        'MaxFilter': {
            'standard_settings': {
                'trans_conditions': [''],
                'trans_option': 'continuous',
                'merge_runs': True,
                'empty_room_files': ['empty_room_before.fif', 'empty_room_after.fif'],
                'sss_files': [''],
                'autobad': True,
                'badlimit': '7',
                'bad_channels': [''],
                'tsss_default': True,
                'correlation': '0.98',
                'movecomp_default': True,
                'subjects_to_skip': ['']
            },
            'advanced_settings': {
                'force': False,
                'downsample': False,
                'downsample_factor': '4',
                'apply_linefreq': False,
                'linefreq_Hz': '50',
                'maxfilter_version': '/neuro/bin/util/maxfilter',
                'MaxFilter_commands': '',
                'debug': False
            }
        },
        'BIDS': {
            'Dataset_description': 'dataset_description.json',
            'Participants': 'participants.tsv',
            'Participants_mapping_file': 'participant_mapping_example.csv',
            'Conversion_file': 'bids_conversion.tsv',
            'Overwrite_conversion': False,
            'Original_subjID_name': 'old_subject_id',
            'New_subjID_name': 'new_subject_id',
            'Original_session_name': 'old_session_id',
            'New_session_name': 'new_session_id',
            'overwrite': False,
            'dataset_type': 'raw',
            'data_license': '',
            'authors': '',
            'acknowledgements': '',
            'how_to_acknowledge': '',
            'funding': '',
            'ethics_approvals': '',
            'references_and_links': '',
            'doi': 'doi:<insert_doi>'
        }
    }
    return config

def rename_legacy_keys(config: dict) -> dict:
    """Rename legacy keys in the configuration dictionary.
    Preserves insertion order. Also normalises legacy values (e.g. continous→continuous).
    """
    legacy_keys = {
        'RUN': {
            # Resolve oldest key directly to final name to avoid a broken two-step chain
            'Add HPI coregistration': 'opm_preprocess',
            'Copy to Cerberos':       'copy_raw',
            'OPM preprocessing':      'opm_preprocess',
            'Sync to CIR':            'sync',
        },
        'Project': {
            'Sinuhe raw': 'sinuhe_raw',
            'Kaptah raw': 'kaptah_raw',
            'Stimuli':    'stimulus',
            'CIR-ID':     'cir_id',
            'Logfile':    'logfile',
        }
    }

    def replace_key_preserve_order(d: dict, old: str, new: str) -> dict:
        new_dict = {}
        for k, v in d.items():
            if k == old:
                if new not in d:
                    new_dict[new] = v
            else:
                new_dict[k] = v
        return new_dict

    def apply_mapping(cfg_node: dict, mapping_node: dict) -> dict:
        node = dict(cfg_node)
        for map_key, map_val in mapping_node.items():
            if isinstance(map_val, str):
                if map_key in node:
                    node = replace_key_preserve_order(node, map_key, map_val)
            elif isinstance(map_val, dict):
                if map_key in node and isinstance(node[map_key], dict):
                    node[map_key] = apply_mapping(node[map_key], map_val)
                else:
                    for child_key, child_val in list(node.items()):
                        if isinstance(child_val, dict):
                            node[child_key] = apply_mapping(child_val, {map_key: map_val})
        return node

    config = apply_mapping(config, legacy_keys)

    # Normalise legacy value: 'continous' → 'continuous'
    try:
        mf_std = config.get('MaxFilter', {}).get('standard_settings', {})
        if mf_std.get('trans_option') == 'continous':
            mf_std['trans_option'] = 'continuous'
    except Exception:
        pass

    return config


def create_config_file(output_file: str = 'default_config.yml'):
    """Create a default configuration file and save it to disk"""
    try:
        config_data = create_default_config()
        if output_file.endswith('.json'):
            with open(output_file, 'w') as f:
                json.dump(config_data, f, indent=4)
        else:
            if not output_file.endswith(('.yml', '.yaml')):
                output_file += '.yml'
            with open(output_file, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, indent=2)
        return True
    except Exception as e:
        print(f"Error creating config file: {e}")
        return False


class ConfigMainWindow:
    """Tkinter main window for SESHAT configuration editor"""

    def __init__(self, config_file=None):
        self.root = tk.Tk()
        self.root.title("SESHAT - Scripts for Extraction, Synchronisation, HPI + Analog alignment and Transfer")
        self.root.geometry("900x800")
        self.logo_image = None

        self._setup_branding_assets()

        self.config_file = config_file
        self.config_data = {}
        self.widgets = {}
        self.manual_edits = set()
        self.programmatic_update = False
        self._last_project_name = ''
        self._last_root_path = ''
        self.terminal_process = None
        self.config_saved = bool(config_file)
        self.execute_btn = None
        self.abort_btn = None

        if self.config_file:
            self.config_data = self.load_config(self.config_file)
            self.detect_manual_edits()
        else:
            self.config_data = create_default_config()

        self.init_ui()

        self._last_project_name = self.config_data['Project'].get('Name', '').strip() or '<project>'
        self._last_root_path = self.config_data['Project'].get('Root', '').strip() or default_path

        self.update_project_paths()

    def _setup_branding_assets(self):
        """Load branding assets and set window icon when available."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        svg_logo_path = os.path.join(base_dir, 'assets', 'seshat_col_white.svg')
        png_fallback_path = os.path.join(base_dir, 'assets', 'seshat_col_white_2.png')

        for candidate in (svg_logo_path, png_fallback_path):
            if os.path.exists(candidate):
                try:
                    self.logo_image = tk.PhotoImage(file=candidate)
                    self.root.iconphoto(True, self.logo_image)
                    self.logo_path = candidate
                    break
                except tk.TclError:
                    self.logo_image = None

    def init_ui(self):
        """Initialize the user interface"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=2, pady=5)

        if self.logo_image is not None:
            logo_label = ttk.Label(main_frame, image=self.logo_image)
            logo_label.pack(anchor='center', pady=(2, 8))

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill='both', expand=True)

        self.create_project_tab()
        self.create_opm_tab()
        # self.create_maxfilter_tab()
        # self.create_bids_tab()
        self.create_run_tab()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', padx=(4, 4), pady=(10, 0))

        ttk.Button(button_frame, text="Cancel", command=self.root.quit).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="Save", command=self.save_config).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="Save As...", command=self.save_as_config).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="Open", command=self.open_config).pack(side='right', padx=(5, 0))

        self.status_label = ttk.Label(main_frame, text=f"Config file: {self.config_file if self.config_file else 'None'}")
        self.status_label.pack(anchor='w', pady=(5, 0))

        if self.config_saved:
            self.mark_config_saved()
        else:
            self.mark_config_changed()

    def create_scrollable_frame(self, parent):
        """Create a scrollable frame"""
        canvas = tk.Canvas(parent, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', on_canvas_configure)

        canvas.pack(side="left", fill="both", expand=True, padx=0, pady=0)
        scrollbar.pack(side="right", fill="y")

        return scrollable_frame

    def create_form_widget(self, parent, key, value, help_text=None):
        """Create a form widget based on the value type"""
        frame = ttk.Frame(parent)
        frame.pack(fill='x', padx=2, pady=1)

        label = ttk.Label(frame, text=f"{key}:", anchor='e', width=25)
        label.pack(side='left', padx=(2, 2))

        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            widget = ttk.Checkbutton(frame, variable=var)
            widget.var = var
            var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])
        elif isinstance(value, list):
            var = tk.StringVar(value=', '.join(str(v) for v in value))
            widget = ttk.Entry(frame, textvariable=var, width=50)
            widget.var = var
            var.trace_add('write', lambda *args, k=key: [self.update_config_list(k, var.get()), self.mark_config_changed()])
        elif key == 'trans_option':
            var = tk.StringVar(value=str(value))
            widget = ttk.Combobox(frame, textvariable=var, values=['continuous', 'initial'], width=47)
            widget.var = var
            var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])
        elif key == 'maxfilter_version':
            var = tk.StringVar(value=str(value))
            widget = ttk.Combobox(frame, textvariable=var,
                                  values=['/neuro/bin/util/maxfilter', '/neuro/bin/util/mfilter'], width=47)
            widget.var = var
            var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(frame, textvariable=var, width=50)
            widget.var = var
            if key == 'Name':
                def update_name_and_paths(*args):
                    self.update_config_value(key, var.get())
                    self.mark_config_changed()
                    self.update_project_paths()
                var.trace_add('write', update_name_and_paths)
            elif key == 'Root':
                def update_root_and_paths(*args):
                    self.update_config_value(key, var.get())
                    self.mark_config_changed()
                    self.update_project_paths()
                var.trace_add('write', update_root_and_paths)
            elif key in ['Raw', 'BIDS', 'Calibration', 'Crosstalk']:
                # Single consolidated callback guarded by programmatic_update to
                # avoid spurious updates when update_project_paths sets these vars.
                def make_path_callback(field_key, field_var):
                    def cb(*args):
                        if self.programmatic_update:
                            return
                        self.update_config_value(field_key, field_var.get())
                        self.mark_config_changed()
                        self.mark_manual_edit(field_key)
                    return cb
                var.trace_add('write', make_path_callback(key, var))
            else:
                var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])

        widget.pack(side='right', fill='x', expand=True)
        self.widgets[key] = widget

        if help_text:
            help_frame = ttk.Frame(parent)
            help_frame.pack(fill='x', padx=(170, 2), pady=(0, 2))
            help_label = ttk.Label(help_frame, text=help_text, foreground='gray', font=('TkDefaultFont', 8))
            help_label.pack(anchor='w')

    def create_run_form_widget(self, parent, key, value):
        """Create a form widget for RUN items using human-readable labels"""
        frame = ttk.Frame(parent)
        frame.pack(fill='x', padx=0, pady=1)

        label = RUN_LABELS.get(key, key)
        var = tk.BooleanVar(value=value)
        widget = ttk.Checkbutton(frame, text=label, variable=var)
        widget.var = var
        var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])
        widget.pack(anchor='w')
        self.widgets[key] = widget

    def create_project_tab(self):
        """Create the Project configuration tab"""
        project_frame = ttk.Frame(self.notebook)
        self.notebook.add(project_frame, text="Project")

        project_notebook = ttk.Notebook(project_frame)
        project_notebook.pack(fill='both', expand=True, padx=2, pady=2)

        standard_frame = ttk.Frame(project_notebook)
        project_notebook.add(standard_frame, text="Standard Settings")
        standard_scrollable = self.create_scrollable_frame(standard_frame)

        # Phase 2.5: updated to new key names
        standard_keys = ['Name', 'cir_id', 'Description', 'Tasks', 'sinuhe_raw', 'kaptah_raw', 'stimulus', 'Polhemus']
        standard_help = {
            'Name':        'Name of project',
            'cir_id':      'CIR ID of the project, used for data management',
            'Description': 'Brief description of the project',
            'Tasks':       'Comma-separated list of experimental tasks',
            'sinuhe_raw':  'Path to project raw data directory on Sinuhe (squid acquisition)',
            'kaptah_raw':  'Path to project raw data directory on Kaptah (opm acquisition)',
            'stimulus':    'Path to project stimulus/presentation data on Stimulus PC',
            'Polhemus':    'Path to the project polhemus digitisation directory on /neuro/data/polhemus/',
        }

        for key in standard_keys:
            if key in self.config_data['Project']:
                value = self.config_data['Project'][key]
                help_text = standard_help.get(key)
                self.create_form_widget(standard_scrollable, key, value, help_text)

        advanced_frame = ttk.Frame(project_notebook)
        project_notebook.add(advanced_frame, text="Advanced Settings")
        advanced_scrollable = self.create_scrollable_frame(advanced_frame)

        # Phase 2.5: updated to new key name 'logfile'
        advanced_keys = [
            'InstitutionName', 'InstitutionAddress', 'InstitutionDepartmentName',
            'Root', 'Raw', 'BIDS', 'Calibration', 'Crosstalk', 'logfile'
        ]
        advanced_help = {
            'InstitutionName':           'Name of the institution',
            'InstitutionAddress':        'Address of the institution',
            'InstitutionDepartmentName': 'Department name',
            'Root':        'Root directory for project data',
            'Raw':         'Raw-path relative to project directory',
            'BIDS':        'BIDS-path relative to project directory',
            'Calibration': 'Path to SSS calibration file relative to project directory',
            'Crosstalk':   'Path to SSS crosstalk file relative to project directory',
            'logfile':     'Name of the log file',
        }

        for key in advanced_keys:
            if key in self.config_data['Project']:
                value = self.config_data['Project'][key]
                help_text = advanced_help.get(key)
                self.create_form_widget(advanced_scrollable, key, value, help_text)

    def create_opm_tab(self):
        """Create the OPM configuration tab"""
        opm_frame = ttk.Frame(self.notebook)
        self.notebook.add(opm_frame, text="OPM")
        opm_scrollable = self.create_scrollable_frame(opm_frame)

        opm_help = {
            'rename_analog_channels': 'Rename analog channels using a mapping file',
            'polhemus':       'Name(s) of fif-file(s) with Polhemus coregistration data',
            'hpi_names':      'Comma-separated list of names of HPI recording',
            'frequency':      'Frequency of the HPI in Hz',
            'downsample_to_hz': 'Downsample OPM data to this frequency',
            'overwrite':      'Overwrite existing OPM data files',
            'plot':           'Store a plot of the OPM data after processing',
        }

        for key, value in self.config_data['OPM'].items():
            help_text = opm_help.get(key)
            self.create_form_widget(opm_scrollable, key, value, help_text)

    def create_run_tab(self):
        """Create the RUN configuration tab"""
        run_frame = ttk.Frame(self.notebook)
        self.notebook.add(run_frame, text="RUN")

        run_settings_frame = ttk.LabelFrame(run_frame, text="Pipeline Steps")
        run_settings_frame.pack(fill='x', padx=5, pady=5)

        skip_keys = {'Run BIDS conversion', 'Run Maxfilter'}
        for key, value in self.config_data['RUN'].items():
            if key in skip_keys:
                continue
            self.create_run_form_widget(run_settings_frame, key, value)

        execute_frame = ttk.Frame(run_frame)
        execute_frame.pack(fill='x', padx=5, pady=5)

        self.execute_btn = ttk.Button(
            execute_frame,
            text="Save to Execute" if not self.config_saved else "Execute Pipeline",
            command=self.execute_pipeline,
        )
        self.execute_btn.pack(side='left', anchor='w')
        self.execute_btn.configure(state='disabled' if not self.config_saved else 'normal')

        self.abort_btn = ttk.Button(execute_frame, text="Abort", command=self.abort_pipeline, state='disabled')
        self.abort_btn.pack(side='left', padx=(10, 0), anchor='w')

        progress_frame = ttk.Frame(run_frame)
        progress_frame.pack(fill='x', padx=5, pady=(5, 0))

        self.progress_label = ttk.Label(progress_frame, text="Ready", font=('TkDefaultFont', 9))
        self.progress_label.pack(anchor='w', pady=(0, 2))

        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=300)
        self.progress_bar.pack(fill='x', pady=(0, 5))

        terminal_frame = ttk.LabelFrame(run_frame, text="Terminal Output")
        terminal_frame.pack(fill='both', expand=True, padx=5, pady=5)

        self.terminal_output = scrolledtext.ScrolledText(
            terminal_frame, height=15, state='disabled',
            bg='black', fg='white', insertbackground='green',
            selectbackground='gray30', selectforeground='white',
            font=('Courier', 10),
        )
        self.terminal_output.pack(fill='both', expand=True, padx=5, pady=5)

        self.terminal_output.configure(state='normal')
        self.terminal_output.insert('end', "Terminal output will appear here...\n")
        self.terminal_output.configure(state='disabled')

    def update_config_value(self, key, value):
        """Update configuration value"""
        for section in ['RUN', 'Project', 'OPM', 'MaxFilter', 'BIDS']:
            if section in self.config_data:
                if key in self.config_data[section]:
                    self.config_data[section][key] = value
                    return
                elif section == 'MaxFilter':
                    for subsection in ['standard_settings', 'advanced_settings']:
                        if key in self.config_data[section][subsection]:
                            self.config_data[section][subsection][key] = value
                            return

    def update_config_list(self, key, text):
        """Update configuration list value from comma-separated text"""
        value = [item.strip() for item in text.split(',') if item.strip()]
        self.update_config_value(key, value)

    def mark_manual_edit(self, key):
        """Mark a field as manually edited (only if not programmatic update)"""
        if not self.programmatic_update:
            self.manual_edits.add(key)

    def detect_manual_edits(self):
        """Detect which path fields have been manually edited based on their current values"""
        project_name = self.config_data['Project'].get('Name', '').strip()
        root_path = self.config_data['Project'].get('Root', '').strip()

        if not root_path:
            root_path = default_path

        display_project = project_name if project_name else '<project>'

        expected_paths = {
            'Raw':         os.path.join(root_path, display_project, 'raw'),
            'BIDS':        os.path.join(root_path, display_project, 'BIDS'),
            'Calibration': os.path.join(root_path, display_project, 'databases', 'sss', 'sss_cal.dat'),
            'Crosstalk':   os.path.join(root_path, display_project, 'databases', 'ctc', 'ct_sparse.fif'),
        }

        for field, expected_path in expected_paths.items():
            current_path = self.config_data['Project'].get(field, '')
            if current_path != expected_path:
                self.manual_edits.add(field)

        self._last_project_name = display_project
        self._last_root_path = root_path

    def update_project_paths(self, changed_value=None):
        """Update project-related paths when project name or root changes"""
        if self.programmatic_update:
            return

        project_name = self.config_data['Project'].get('Name', '').strip()
        root_path = self.config_data['Project'].get('Root', '').strip()

        if not root_path:
            root_path = default_path

        display_project = project_name if project_name else '<project>'

        self.programmatic_update = True

        try:
            old_project = getattr(self, '_last_project_name', '<project>')
            old_root = getattr(self, '_last_root_path', root_path)

            if old_project == display_project and old_root == root_path:
                return

            project_being_filled = (old_project == '<project>' and display_project != '<project>')

            path_patterns = {
                'Raw':         'raw',
                'BIDS':        'BIDS',
                'Calibration': os.path.join('databases', 'sss', 'sss_cal.dat'),
                'Crosstalk':   os.path.join('databases', 'ctc', 'ct_sparse.fif'),
            }

            for field, suffix in path_patterns.items():
                current_path = self.config_data['Project'].get(field, '')

                if field not in self.manual_edits or project_being_filled:
                    new_path = os.path.join(root_path, display_project, suffix)
                    if project_being_filled and field in self.manual_edits:
                        self.manual_edits.discard(field)
                else:
                    new_path = self.smart_path_update(current_path, old_root, old_project, root_path, display_project)

                self.config_data['Project'][field] = new_path

                if field in self.widgets:
                    self.widgets[field].var.set(new_path)

            if self.config_data['Project'].get('Root', '') != root_path:
                self.config_data['Project']['Root'] = root_path
                if 'Root' in self.widgets:
                    self.widgets['Root'].var.set(root_path)

            self._last_project_name = display_project
            self._last_root_path = root_path

        finally:
            self.programmatic_update = False

    def smart_path_update(self, current_path, old_root, old_project, new_root, new_project):
        """Intelligently update path components while preserving manual customizations"""
        if not current_path:
            return os.path.join(new_root, new_project)

        updated_path = current_path

        if '<project>' in updated_path and new_project != '<project>':
            updated_path = updated_path.replace('<project>', new_project)

        if old_root and old_root != new_root and old_root in updated_path:
            old_root_norm = os.path.normpath(old_root)
            new_root_norm = os.path.normpath(new_root)
            if updated_path.startswith(old_root_norm):
                updated_path = updated_path.replace(old_root_norm, new_root_norm, 1)

        if (old_project != new_project and
                old_project != '<project>' and new_project != '<project>' and
                old_project in updated_path):
            path_parts = updated_path.split(os.sep)
            for i, part in enumerate(path_parts):
                if part == old_project:
                    path_parts[i] = new_project
                    break
            updated_path = os.sep.join(path_parts)

        return os.path.normpath(updated_path)

    def mark_config_changed(self):
        """Mark configuration as changed and update UI accordingly"""
        self.config_saved = False
        if self.execute_btn:
            self.execute_btn.configure(text="Save to Execute", state='disabled')
        if self.abort_btn:
            self.abort_btn.configure(state='disabled')

    def mark_config_saved(self):
        """Mark configuration as saved and update UI accordingly"""
        self.config_saved = True
        if self.execute_btn:
            self.execute_btn.configure(text="Execute Pipeline", state='normal')
        if self.abort_btn:
            self.abort_btn.configure(state='disabled')

    def load_config(self, config_file=None):
        """Load configuration from file"""
        if not config_file:
            return create_default_config()

        try:
            if hasattr(config_file, 'name'):
                filename = config_file.name
            else:
                filename = config_file

            if filename.endswith('.yml') or filename.endswith('.yaml'):
                with open(filename, 'r') as file:
                    config = yaml.safe_load(file)
            elif filename.endswith('.json'):
                with open(filename, 'r') as file:
                    config = json.load(file)
            else:
                return create_default_config()

            if config:
                if 'Project' in config and 'Tasks' in config['Project']:
                    if isinstance(config['Project']['Tasks'], str):
                        config['Project']['Tasks'] = config['Project']['Tasks'].split(',')
                config = rename_legacy_keys(config)

            return config if config else create_default_config()

        except Exception as e:
            messagebox.showerror("Error", f"Error loading config: {e}")
            return create_default_config()

    def save_config(self):
        """Save current configuration"""
        if not self.config_file:
            self.save_as_config()
            return

        if os.path.exists(self.config_file):
            response = messagebox.askyesno(
                "Overwrite File?",
                f"The file '{os.path.basename(self.config_file)}' already exists.\n\n"
                f"Do you want to overwrite it?",
                icon='warning',
            )
            if not response:
                return

        try:
            if self.config_file.endswith('.yml') or self.config_file.endswith('.yaml'):
                with open(self.config_file, 'w') as file:
                    yaml.dump(self.config_data, file, default_flow_style=False, sort_keys=False)
            elif self.config_file.endswith('.json'):
                with open(self.config_file, 'w') as file:
                    json.dump(self.config_data, file, indent=4)

            self.status_label.configure(text=f"Config saved to: {self.config_file}")
            self.mark_config_saved()

        except Exception as e:
            messagebox.showerror("Error", f"Error saving config: {e}")

    def save_as_config(self):
        """Save configuration as new file"""
        filename = filedialog.asksaveasfilename(
            initialdir=default_path,
            title="Save Configuration File",
            filetypes=[("YAML files", "*.yml *.yaml"), ("JSON files", "*.json"), ("All files", "*.*")],
        )

        if filename:
            if not filename.endswith(('.yml', '.yaml', '.json')):
                filename += '.yml'
            self.config_file = filename
            self.save_config()

    def open_config(self):
        """Open configuration file"""
        filename = filedialog.askopenfilename(
            initialdir=default_path,
            title="Open Configuration File",
            filetypes=[
                ("Config files", "*.yml *.yaml *.json"),
                ("YAML files", "*.yml *.yaml"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            try:
                new_config = self.load_config(filename)
                if new_config:
                    self.config_data = new_config
                    self.config_file = filename
                    self.manual_edits.clear()
                    self.detect_manual_edits()
                    self.status_label.configure(text=f"Config loaded from: {filename}")
                    self.update_all_widgets()
                    self.mark_config_saved()
            except Exception as e:
                messagebox.showerror("Error", f"Error opening config: {e}")

    def update_all_widgets(self):
        """Update all widgets with current config values"""
        for key, widget in self.widgets.items():
            value = None
            for section in ['RUN', 'Project', 'OPM', 'MaxFilter', 'BIDS']:
                if section in self.config_data:
                    if key in self.config_data[section]:
                        value = self.config_data[section][key]
                        break
                    elif section == 'MaxFilter':
                        for subsection in ['standard_settings', 'advanced_settings']:
                            if key in self.config_data[section][subsection]:
                                value = self.config_data[section][subsection][key]
                                break

            if value is not None:
                if hasattr(widget, 'var'):
                    if isinstance(value, list):
                        widget.var.set(', '.join(str(v) for v in value))
                    else:
                        widget.var.set(str(value) if not isinstance(value, bool) else value)

    def execute_pipeline(self):
        """Execute the pipeline"""
        self.terminal_output.configure(state='normal')
        self.terminal_output.delete(1.0, 'end')
        self.terminal_output.insert('end', "Executing pipeline...\n")
        self.terminal_output.configure(state='disabled')

        self.progress_bar.stop()
        self.progress_bar.configure(mode='determinate')
        self.progress_bar['value'] = 0
        self.progress_label['text'] = "Starting..."

        self.execute_btn.configure(state='disabled')
        self.abort_btn.configure(state='normal')

        # Phase 1.5: use 'python -m seshat.cli run' so we always use the same
        # interpreter as the GUI, regardless of whether 'seshat' is on PATH.
        cmd = [sys.executable, '-m', 'seshat.cli', 'run']
        if self.config_file:
            cmd += ['--config', self.config_file]

        def run_pipeline():
            try:
                env = os.environ.copy()
                env['FORCE_COLOR'] = '1'
                env['PYTHONUNBUFFERED'] = '1'

                self.terminal_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                    encoding='utf-8',
                    errors='replace',
                    env=env,
                )

                for line in iter(self.terminal_process.stdout.readline, ''):
                    if line:
                        cleaned_line = self.clean_terminal_output(line)
                        self.root.after(0, self.append_output, cleaned_line)

                self.terminal_process.wait()
                exit_code = self.terminal_process.returncode
                self.terminal_process = None

                self.root.after(0, self.append_output, f"\nProcess finished with exit code: {exit_code}\n")
                self.root.after(0, self.reset_buttons)

            except Exception as e:
                self.terminal_process = None
                self.root.after(0, self.append_output, f"Error running pipeline: {e}\n")
                self.root.after(0, self.reset_buttons)

        threading.Thread(target=run_pipeline, daemon=True).start()

    def abort_pipeline(self):
        """Abort the running pipeline"""
        if self.terminal_process:
            try:
                self.terminal_process.terminate()
                self.append_output("\n*** Pipeline execution aborted by user ***\n")

                def force_kill():
                    if self.terminal_process and self.terminal_process.poll() is None:
                        self.terminal_process.kill()
                        self.append_output("*** Process forcefully terminated ***\n")

                self.root.after(1000, force_kill)

            except Exception as e:
                self.append_output(f"Error aborting process: {e}\n")
            finally:
                self.reset_buttons()

    def clean_terminal_output(self, text):
        """Clean problematic Unicode characters from terminal output"""
        unicode_replacements = {
            '\u258f': '▏', '\u258e': '▎', '\u258d': '▍', '\u258c': '▌',
            '\u258b': '▋', '\u258a': '▊', '\u2589': '▉', '\u2588': '█',
            '\u2590': '▐', '\u2591': '░', '\u2592': '▒', '\u2593': '▓',
            '\u25cf': '●', '\u25cb': '○', '\u25aa': '▪', '\u25ab': '▫',
            '\u2502': '│', '\u2500': '─', '\u250c': '┌', '\u2510': '┐',
            '\u2514': '└', '\u2518': '┘', '\u251c': '├', '\u2524': '┤',
            '\u252c': '┬', '\u2534': '┴', '\u253c': '┼',
        }

        for unicode_char, replacement in unicode_replacements.items():
            text = text.replace(unicode_char, replacement)

        ansi_pattern = re.compile(r'(\033\[[0-9;]*m)')
        ansi_codes = ansi_pattern.findall(text)
        text_with_placeholders = ansi_pattern.sub('\x00ANSI\x00', text)
        text_cleaned = re.sub(r'[^\x20-\x7E\n\t\r\x00]', '?', text_with_placeholders)
        for code in ansi_codes:
            text_cleaned = text_cleaned.replace('\x00ANSI\x00', code, 1)

        return text_cleaned

    def reset_buttons(self):
        """Reset button states after pipeline execution"""
        self.execute_btn.configure(state='normal')
        self.abort_btn.configure(state='disabled')

    def append_output(self, text):
        """Append text to terminal output with ANSI color support (thread-safe)"""
        self.terminal_output.configure(state='normal')
        apply_ansi_colors_to_tk(self.terminal_output, text)
        self.terminal_output.see('end')
        self.terminal_output.configure(state='disabled')
        self.update_progress_from_text(text)
        self.root.update_idletasks()

    def update_progress_from_text(self, text):
        """Extract progress information from terminal output and update progress bar"""
        match = re.search(r'(\d+)/(\d+)', text)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            if total > 0:
                percentage = (current / total) * 100
                self.progress_bar['value'] = percentage
                self.progress_bar['maximum'] = 100
                try:
                    current_mb = current / (1024.0 * 1024.0)
                    total_mb = total / (1024.0 * 1024.0)
                    self.progress_label['text'] = f"{current_mb:.1f} MB / {total_mb:.1f} MB ({percentage:.1f}%)"
                except Exception:
                    self.progress_label['text'] = f"Progress: {current}/{total} ({percentage:.1f}%)"
                return

        match = re.search(r'(\d+)%', text)
        if match:
            percentage = int(match.group(1))
            self.progress_bar['value'] = percentage
            self.progress_bar['maximum'] = 100
            self.progress_label['text'] = f"Progress: {percentage}%"
            return

        match = re.search(r'(\d+)it \[[\d:]+<[\d:]+', text)
        if match:
            if self.progress_bar['mode'] != 'indeterminate':
                self.progress_bar.configure(mode='indeterminate')
                self.progress_bar.start(10)
            return

        if 'finished' in text.lower() or 'completed' in text.lower() or 'done' in text.lower():
            self.progress_bar.stop()
            self.progress_bar.configure(mode='determinate')
            self.progress_bar['value'] = 100
            self.progress_label['text'] = "Complete!"

    def show(self):
        """Show the window"""
        self.root.mainloop()

    def quit(self):
        """Quit the application"""
        self.root.quit()


def args_parser():
    parser = argparse.ArgumentParser(
        description='Configuration script for SESHAT pipeline (Tkinter version).',
        add_help=True,
    )
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    return parser.parse_args()


def config_UI(config_file: str = None):
    """Launch the configuration GUI and return the configuration"""
    window = ConfigMainWindow(config_file=config_file)
    window.show()
    return window.config_data


def main(config_file: str = None):
    """Main entry point"""
    args = args_parser()
    config_file = args.config or config_file
    window = ConfigMainWindow(config_file=config_file)
    window.show()


if __name__ == "__main__":
    main()
