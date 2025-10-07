import yaml
import json
import sys
import os
import argparse
import re
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

default_path = '/neuro/data/local'


def create_default_config():
    """Create default configuration dictionary without GUI dependencies"""
    config = {
        'RUN': {
            'Copy to Cerberos': True,
            'Add HPI coregistration': True,
            'Run Maxfilter': True,
            'Run BIDS conversion': True,
            'Sync to CIR': True
        },
        'Project': {
            'Name': '',
            'CIR-ID': '',
            'InstitutionName': 'Karolinska Institutet',
            'InstitutionAddress': 'Nobels vag 9, 171 77, Stockholm, Sweden',
            'InstitutionDepartmentName': 'Department of Clinical Neuroscience (CNS)',
            'Description': 'project for MEG data',
            'Tasks': [''],
            'Sinuhe raw': '/neuro/data/sinuhe/<project_path_on_sinuhe>',
            'Kaptah raw': '/neuro/data/kaptah/<project_path_on_kaptah>',
            'Root': default_path,
            'Raw': f'{default_path}/<project>/raw',
            'BIDS': f'{default_path}/<project>/BIDS',
            'Calibration': f'{default_path}/<project>/databases/sss/sss_cal.dat',
            'Crosstalk': f'{default_path}/<project>/databases/ctc/ct_sparse.fif',
            'Logfile': 'pipeline_log.log'
        },
        'OPM': {
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
                'trans_option': 'continous',
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


def create_config_file(output_file: str = 'default_config.yml'):
    """Create a default configuration file and save it to disk"""
    try:
        # Use the standalone function to avoid GUI dependencies
        config_data = create_default_config()
        
        # Save to file based on extension
        if output_file.endswith('.json'):
            with open(output_file, 'w') as f:
                json.dump(config_data, f, indent=4)
        else:
            # Default to YAML format
            if not output_file.endswith(('.yml', '.yaml')):
                output_file += '.yml'
            with open(output_file, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, indent=2)
        
        return True
    except Exception as e:
        print(f"Error creating config file: {e}")
        return False


class ConfigMainWindow:
    """Tkinter main window for NatMEG configuration editor"""
    
    def __init__(self, config_file=None):
        self.root = tk.Tk()
        self.root.title("NatMEG Config Editor")
        self.root.geometry("900x800")
        
        self.config_file = config_file
        self.config_data = {}
        self.widgets = {}  # Store widget references for data binding
        self.manual_edits = set()  # Track manually edited path fields
        self.programmatic_update = False  # Flag to distinguish programmatic vs user edits
        self._last_project_name = ''  # Track previous project name for smart updates
        self._last_root_path = ''  # Track previous root path for smart updates
        self.terminal_process = None
        self.config_saved = bool(config_file)  # True if loading existing config, False for new
        self.execute_btn = None  # Will be set in create_run_tab
        
        # Load configuration
        if self.config_file:
            self.config_data = self.load_config(self.config_file)
            self.detect_manual_edits()  # Detect manual edits in loaded config
        else:
            self.config_data = create_default_config()
        
        self.init_ui()
        
        # Initialize tracking variables
        self._last_project_name = self.config_data['Project'].get('Name', '').strip() or '<project>'
        self._last_root_path = self.config_data['Project'].get('Root', '').strip() or default_path
        
        # Initialize paths after UI is created
        self.update_project_paths()
        
    def init_ui(self):
        """Initialize the user interface"""
        # Create main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=2, pady=5)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill='both', expand=True)
        
        # Create tabs
        self.create_project_tab()
        self.create_opm_tab()
        self.create_maxfilter_tab()
        self.create_bids_tab()
        self.create_run_tab()
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', padx= (4, 4), pady=(10, 0))
        
        # Buttons (reordered: Open, Save As, Save, Cancel)
        ttk.Button(button_frame, text="Cancel", command=self.root.quit).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="Save", command=self.save_config).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="Save As...", command=self.save_as_config).pack(side='right', padx=(5, 0))
        ttk.Button(button_frame, text="Open", command=self.open_config).pack(side='right', padx=(5, 0))
        
        # Status label
        self.status_label = ttk.Label(main_frame, text=f"Config file: {self.config_file if self.config_file else 'None'}")
        self.status_label.pack(anchor='w', pady=(5, 0))
        
        # Set initial execute button state
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
        
        # Bind canvas to update scrollable frame width when canvas resizes
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
        
        # Label
        label = ttk.Label(frame, text=f"{key}:", anchor='e', width=25)
        label.pack(side='left', padx=(2, 2))
        
        # Widget based on value type
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
            widget = ttk.Combobox(frame, textvariable=var, values=['continous', 'initial'], width=47)
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
            # Special handling for project name and root fields to auto-update paths
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
            # Mark path fields as manually edited when user changes them
            elif key in ['Raw', 'BIDS', 'Calibration', 'Crosstalk']:
                var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])
                # Store the key in the lambda to avoid closure issues
                def make_manual_edit_callback(field_key):
                    return lambda *args: self.mark_manual_edit(field_key)
                var.trace_add('write', make_manual_edit_callback(key))
            else:
                var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])
        
        widget.pack(side='right', fill='x', expand=True)
        
        # Store widget reference
        self.widgets[key] = widget
        
        # Add help text on a new line directly under the entry field if provided
        if help_text:
            help_frame = ttk.Frame(parent)
            help_frame.pack(fill='x', padx=(170, 2), pady=(0, 2))
            help_label = ttk.Label(help_frame, text=help_text, foreground='gray', font=('TkDefaultFont', 8))
            help_label.pack(anchor='w')
    
    def create_run_form_widget(self, parent, key, value):
        """Create a form widget for RUN items"""
        frame = ttk.Frame(parent)
        frame.pack(fill='x', padx=0, pady=1)
        
        var = tk.BooleanVar(value=value)
        widget = ttk.Checkbutton(frame, text=key, variable=var)
        widget.var = var
        var.trace_add('write', lambda *args, k=key: [self.update_config_value(k, var.get()), self.mark_config_changed()])
        widget.pack(anchor='w')
        
        # Store widget reference
        self.widgets[key] = widget
    
    def create_project_tab(self):
        """Create the Project configuration tab"""
        project_frame = ttk.Frame(self.notebook)
        self.notebook.add(project_frame, text="Project")
        
        # Create sub-notebook for project tabs
        project_notebook = ttk.Notebook(project_frame)
        project_notebook.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Standard settings tab
        standard_frame = ttk.Frame(project_notebook)
        project_notebook.add(standard_frame, text="Standard Settings")
        standard_scrollable = self.create_scrollable_frame(standard_frame)
        
        
        standard_keys = ['Name', 'CIR-ID', 'Description', 'Tasks', 'Sinuhe raw', 'Kaptah raw']
        standard_help = {
            'Name': 'Name of project',
            'CIR-ID': 'CIR ID of the project, used for data management',
            'Description': 'Brief description of the project',
            'Tasks': 'Comma-separated list of experimental tasks',
            'Sinuhe raw': 'Path to Sinuhe raw data directory',
            'Kaptah raw': 'Path to Kaptah raw data directory'
        }
        
        for key in standard_keys:
            if key in self.config_data['Project']:
                value = self.config_data['Project'][key]
                help_text = standard_help.get(key)
                self.create_form_widget(standard_scrollable, key, value, help_text)
        
        # Advanced settings tab
        advanced_frame = ttk.Frame(project_notebook)
        project_notebook.add(advanced_frame, text="Advanced Settings")
        advanced_scrollable = self.create_scrollable_frame(advanced_frame)
        
        advanced_keys = [
            'InstitutionName', 'InstitutionAddress', 'InstitutionDepartmentName',
            'Root', 'Raw', 'BIDS', 'Calibration', 'Crosstalk', 'Logfile'
        ]
        advanced_help = {
            'InstitutionName': 'Name of the institution',
            'InstitutionAddress': 'Address of the institution',
            'InstitutionDepartmentName': 'Department name',
            'Root': 'Root directory for project data',
            'Raw': 'Raw-path relative to project directory',
            'BIDS': 'BIDS-path relative to project directory',
            'Calibration': 'Path to SSS calibration file relative to project directory',
            'Crosstalk': 'Path to SSS crosstalk file relative to project directory',
            'Logfile': 'Name of the log file'
        }
        
        for key in advanced_keys:
            if key in self.config_data['Project']:
                value = self.config_data['Project'][key]
                help_text = advanced_help.get(key)
                self.create_form_widget(advanced_scrollable, key, value, help_text)
    
    def create_opm_tab(self):
        """Create the OMP configuration tab"""
        opm_frame = ttk.Frame(self.notebook)
        self.notebook.add(opm_frame, text="OPM")
        opm_scrollable = self.create_scrollable_frame(opm_frame)
        
        opm_help = {
            'polhemus': 'Name(s) of fif-file(s) with Polhemus coregistration data',
            'hpi_names': 'Comma-separated list of names of HPI recording',
            'frequency': 'Frequency of the HPI in Hz',
            'downsample_to_hz': 'Downsample OPM data to this frequency',
            'overwrite': 'Overwrite existing OPM data files',
            'plot': 'Store a plot of the OPM data after processing'
        }
        
        for key, value in self.config_data['OPM'].items():
            help_text = opm_help.get(key)
            self.create_form_widget(opm_scrollable, key, value, help_text)
    
    def create_maxfilter_tab(self):
        """Create the MaxFilter configuration tab"""
        maxfilter_frame = ttk.Frame(self.notebook)
        self.notebook.add(maxfilter_frame, text="MaxFilter")
        
        # Create sub-notebook
        maxfilter_notebook = ttk.Notebook(maxfilter_frame)
        maxfilter_notebook.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Standard settings
        standard_frame = ttk.Frame(maxfilter_notebook)
        maxfilter_notebook.add(standard_frame, text="Standard Settings")
        standard_scrollable = self.create_scrollable_frame(standard_frame)
        
        standard_help = {
            'trans_conditions': 'Comma-separated list of tasks which should be transformed to average head',
            'trans_option': 'Option for transformation, either "continous" for average or "initial" for initial head position',
            'merge_runs': 'Use multiple runs to calculate average head position',
            'empty_room_files': 'Comma-separated list of empty room files to use for MaxFilter processing',
            'sss_files': 'Tasks which should only be sss filtered',
            'autobad': 'Automatically detect and exclude bad channels',
            'badlimit': 'Bad channel threshold for processing',
            'bad_channels': 'Comma-separated list of bad channels to exclude from processing',
            'tsss_default': 'Use default TSSS settings',
            'correlation': 'Correlation threshold for TSSS',
            'movecomp_default': 'Use default movecomp settings',
            'subjects_to_skip': 'Comma-separated list of subject IDs to skip during MaxFilter processing'
        }
        
        for key, value in self.config_data['MaxFilter']['standard_settings'].items():
            help_text = standard_help.get(key)
            self.create_form_widget(standard_scrollable, key, value, help_text)
        
        # Advanced settings
        advanced_frame = ttk.Frame(maxfilter_notebook)
        maxfilter_notebook.add(advanced_frame, text="Advanced Settings")
        advanced_scrollable = self.create_scrollable_frame(advanced_frame)
        
        advanced_help = {
            'force': 'Force MaxFilter to run even if bad channels are detected',
            'downsample': 'Downsample data',
            'downsample_factor': 'Factor to downsample data by',
            'apply_linefreq': 'Apply line frequency filtering',
            'linefreq_Hz': 'Line frequency in Hz to apply filtering',
            'maxfilter_version': 'Path to MaxFilter executable',
            'MaxFilter_commands': 'Additional MaxFilter commands to run',
            'debug': 'Enable debug mode for MaxFilter'
        }
        
        for key, value in self.config_data['MaxFilter']['advanced_settings'].items():
            help_text = advanced_help.get(key)
            self.create_form_widget(advanced_scrollable, key, value, help_text)
    
    def create_bids_tab(self):
        """Create the BIDS configuration tab"""
        bids_frame = ttk.Frame(self.notebook)
        self.notebook.add(bids_frame, text="BIDS")
        
        # Create sub-notebook
        bids_notebook = ttk.Notebook(bids_frame)
        bids_notebook.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Standard settings
        standard_frame = ttk.Frame(bids_notebook)
        bids_notebook.add(standard_frame, text="Standard Settings")
        standard_scrollable = self.create_scrollable_frame(standard_frame)
        
        standard_bids_keys = [
            'Dataset_description', 'Participants', 'Participants_mapping_file', 
            'Conversion_file', 'Overwrite_conversion', 'Original_subjID_name',
            'New_subjID_name', 'Original_session_name', 'New_session_name', 'overwrite'
        ]
        
        standard_bids_help = {
            'Dataset_description': 'Path to dataset_description.json file',
            'Participants': 'Path to participants.tsv file',
            'Participants_mapping_file': 'Path to participant mapping CSV file',
            'Conversion_file': 'Path to conversion file',
            'Overwrite_conversion': 'Overwrite existing conversion files',
            'Original_subjID_name': 'Name of the original subject ID column in the mapping file',
            'New_subjID_name': 'Name of the new subject ID column in the mapping file',
            'Original_session_name': 'Name of the original session ID column in the mapping file',
            'New_session_name': 'Name of the new session ID column in the mapping file',
            'overwrite': 'Overwrite existing BIDS files'
        }
        
        for key in standard_bids_keys:
            if key in self.config_data['BIDS']:
                value = self.config_data['BIDS'][key]
                help_text = standard_bids_help.get(key)
                self.create_form_widget(standard_scrollable, key, value, help_text)
        
        # Dataset description
        dataset_frame = ttk.Frame(bids_notebook)
        bids_notebook.add(dataset_frame, text="Dataset Description")
        dataset_scrollable = self.create_scrollable_frame(dataset_frame)
        
        dataset_keys = [
            'dataset_type', 'data_license', 'authors', 'acknowledgements',
            'how_to_acknowledge', 'funding', 'ethics_approvals', 
            'references_and_links', 'doi'
        ]
        
        dataset_help = {
            'dataset_type': 'Type of dataset (e.g., "raw", "derivative")',
            'data_license': 'License under which the data is made available',
            'authors': 'List of individuals who contributed to the creation/curation of the dataset',
            'acknowledgements': 'Text acknowledging contributions',
            'how_to_acknowledge': 'Instructions on how researchers should acknowledge this dataset',
            'funding': 'List of sources of funding',
            'ethics_approvals': 'List of ethics committee approvals',
            'references_and_links': 'List of references, publications, and links',
            'doi': 'Digital Object Identifier of the dataset'
        }
        
        for key in dataset_keys:
            if key in self.config_data['BIDS']:
                value = self.config_data['BIDS'][key]
                help_text = dataset_help.get(key)
                self.create_form_widget(dataset_scrollable, key, value, help_text)
    
    def create_run_tab(self):
        """Create the RUN configuration tab"""
        run_frame = ttk.Frame(self.notebook)
        self.notebook.add(run_frame, text="RUN")
        
        # RUN settings
        run_settings_frame = ttk.LabelFrame(run_frame, text="Pipeline Steps")
        run_settings_frame.pack(fill='x', padx=5, pady=5)
        
        for key, value in self.config_data['RUN'].items():
            self.create_run_form_widget(run_settings_frame, key, value)
        
        # Execute button
        execute_frame = ttk.Frame(run_frame)
        execute_frame.pack(fill='x', padx=5, pady=5)
        
        self.execute_btn = ttk.Button(execute_frame, 
                                     text="Save to Execute" if not self.config_saved else "Execute Pipeline",
                                     command=self.execute_pipeline)
        self.execute_btn.pack(anchor='w')
        self.execute_btn.configure(state='disabled' if not self.config_saved else 'normal')
        
        # Terminal output
        terminal_frame = ttk.LabelFrame(run_frame, text="Terminal Output")
        terminal_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.terminal_output = scrolledtext.ScrolledText(
            terminal_frame, 
            height=15, 
            state='disabled',
            bg='black',
            fg='white',
            insertbackground='green',
            selectbackground='gray30',
            selectforeground='white',
            font=('Courier', 10)
        )
        self.terminal_output.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Add initial text
        self.terminal_output.configure(state='normal')
        self.terminal_output.insert('end', "Terminal output will appear here...\n")
        self.terminal_output.configure(state='disabled')
    
    def update_config_value(self, key, value):
        """Update configuration value"""
        # Find the correct nested location for the key
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
        
        # Check each path field against expected auto-generated pattern
        expected_paths = {
            'Raw': os.path.join(root_path, display_project, "raw"),
            'BIDS': os.path.join(root_path, display_project, "BIDS"),
            'Calibration': os.path.join(root_path, display_project, "databases", "sss", "sss_cal.dat"),
            'Crosstalk': os.path.join(root_path, display_project, "databases", "ctc", "ct_sparse.fif")
        }
        
        for field, expected_path in expected_paths.items():
            current_path = self.config_data['Project'].get(field, '')
            # If current path doesn't match expected auto-generated path, mark as manual edit
            if current_path != expected_path:
                self.manual_edits.add(field)
        
        # Update tracking variables after detection
        self._last_project_name = display_project
        self._last_root_path = root_path
    
    def update_project_paths(self, changed_value=None):
        """Update project-related paths when project name or root changes"""
        # Prevent recursion
        if self.programmatic_update:
            return
            
        # Get current values from config data (should be updated before this call)
        project_name = self.config_data['Project'].get('Name', '').strip()
        root_path = self.config_data['Project'].get('Root', '').strip()
        
        # If no root, use default
        if not root_path:
            root_path = default_path
        
        # Use project name or placeholder
        display_project = project_name if project_name else '<project>'
        
        # Set flag to prevent recursion
        self.programmatic_update = True
        
        try:
            # Get previous values for comparison
            old_project = getattr(self, '_last_project_name', '<project>')
            old_root = getattr(self, '_last_root_path', root_path)
            
            # Only update if something actually changed
            if old_project == display_project and old_root == root_path:
                return
            
            # Special case: if project name is being filled in (from empty/placeholder to actual name)
            # we should update all paths that contain <project> regardless of manual_edits status
            project_being_filled = (old_project == '<project>' and display_project != '<project>')
            
            # Define path patterns
            path_patterns = {
                'Raw': 'raw',
                'BIDS': 'BIDS', 
                'Calibration': os.path.join('databases', 'sss', 'sss_cal.dat'),
                'Crosstalk': os.path.join('databases', 'ctc', 'ct_sparse.fif')
            }
            
            # Update each path field
            for field, suffix in path_patterns.items():
                current_path = self.config_data['Project'].get(field, '')
                
                if field not in self.manual_edits or project_being_filled:
                    # Auto-generated path OR project name being filled in: create standard path
                    new_path = os.path.join(root_path, display_project, suffix)
                    
                    # If project is being filled in, remove from manual edits so it stays auto-updated
                    if project_being_filled and field in self.manual_edits:
                        self.manual_edits.discard(field)
                else:
                    # Manually edited path: intelligently update components
                    new_path = self.smart_path_update(current_path, old_root, old_project, root_path, display_project)
                
                # Update config data
                self.config_data['Project'][field] = new_path
                
                # Update widget if it exists
                if field in self.widgets:
                    self.widgets[field].var.set(new_path)
            
            # Update root in config if it was defaulted
            if self.config_data['Project'].get('Root', '') != root_path:
                self.config_data['Project']['Root'] = root_path
                if 'Root' in self.widgets:
                    self.widgets['Root'].var.set(root_path)
            
            # Store current values for next comparison
            self._last_project_name = display_project
            self._last_root_path = root_path
            
        finally:
            # Always reset the flag
            self.programmatic_update = False
    
    def smart_path_update(self, current_path, old_root, old_project, new_root, new_project):
        """Intelligently update path components while preserving manual customizations"""
        if not current_path:
            return os.path.join(new_root, new_project)
        
        # Start with the current path
        updated_path = current_path
        
        # FIRST: Always replace <project> placeholder with actual project name
        if '<project>' in updated_path and new_project != '<project>':
            updated_path = updated_path.replace('<project>', new_project)
        
        # SECOND: Handle root directory changes
        if old_root and old_root != new_root and old_root in updated_path:
            old_root_norm = os.path.normpath(old_root)
            new_root_norm = os.path.normpath(new_root)
            
            # Replace root directory if it appears at the start of the path
            if updated_path.startswith(old_root_norm):
                updated_path = updated_path.replace(old_root_norm, new_root_norm, 1)
        
        # THIRD: Handle project name changes (but not from/to <project>)
        if (old_project != new_project and 
            old_project != '<project>' and new_project != '<project>' and
            old_project in updated_path):
            
            # Split path and replace project component
            path_parts = updated_path.split(os.sep)
            for i, part in enumerate(path_parts):
                if part == old_project:
                    path_parts[i] = new_project
                    break
            updated_path = os.sep.join(path_parts)
        
        # Normalize the final path
        return os.path.normpath(updated_path)
    
    def mark_config_changed(self):
        """Mark configuration as changed and update UI accordingly"""
        self.config_saved = False
        if self.execute_btn:
            self.execute_btn.configure(text="Save to Execute", state='disabled')
    
    def mark_config_saved(self):
        """Mark configuration as saved and update UI accordingly"""
        self.config_saved = True
        if self.execute_btn:
            self.execute_btn.configure(text="Execute Pipeline", state='normal')
    
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
                
            # Convert strings to lists where needed
            if config:
                if 'Project' in config and 'Tasks' in config['Project']:
                    if isinstance(config['Project']['Tasks'], str):
                        config['Project']['Tasks'] = config['Project']['Tasks'].split(',')
                
            return config if config else create_default_config()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error loading config: {e}")
            return create_default_config()
    
    def save_config(self):
        """Save current configuration"""
        if not self.config_file:
            self.save_as_config()
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
            filetypes=[("YAML files", "*.yml *.yaml"), ("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            if not filename.endswith(('.yml', '.yaml', '.json')):
                filename += '.yml'  # Default to YAML
            
            self.config_file = filename
            self.save_config()
    
    def open_config(self):
        """Open configuration file"""
        filename = filedialog.askopenfilename(
            initialdir=default_path,
            title="Open Configuration File",
            filetypes=[("Config files", "*.yml *.yaml *.json"), 
                      ("YAML files", "*.yml *.yaml"), 
                      ("JSON files", "*.json"), 
                      ("All files", "*.*")]
        )
        
        if filename:
            try:
                new_config = self.load_config(filename)
                if new_config:
                    self.config_data = new_config
                    self.config_file = filename
                    self.manual_edits.clear()  # Clear first, then detect manual edits
                    self.detect_manual_edits()  # Detect which fields were manually edited
                    self.status_label.configure(text=f"Config loaded from: {filename}")
                    self.update_all_widgets()
                    self.mark_config_saved()  # Mark as saved since we just loaded it
            except Exception as e:
                messagebox.showerror("Error", f"Error opening config: {e}")
    
    def update_all_widgets(self):
        """Update all widgets with current config values"""
        # Update all widgets when a new config is loaded
        for key, widget in self.widgets.items():
            # Find the value in config
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
        
        # Build command
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pipeline_path = os.path.join(base_dir, 'natmeg_pipeline.py')
        
        if not os.path.exists(pipeline_path):
            self.terminal_output.configure(state='normal')
            self.terminal_output.insert('end', "Error: natmeg_pipeline.py not found!\n")
            self.terminal_output.configure(state='disabled')
            return
        
        cmd = [sys.executable, '-u', pipeline_path, 'run']
        if self.config_file:
            cmd += ['--config', self.config_file]
        
        # Start process in a separate thread
        def run_pipeline():
            try:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                         universal_newlines=True, bufsize=1)
                
                for line in iter(process.stdout.readline, ''):
                    if line:
                        self.root.after(0, self.append_output, line)
                
                process.wait()
                self.root.after(0, self.append_output, f"\nProcess finished with exit code: {process.returncode}\n")
            except Exception as e:
                self.root.after(0, self.append_output, f"Error running pipeline: {e}\n")
        
        threading.Thread(target=run_pipeline, daemon=True).start()
    
    def append_output(self, text):
        """Append text to terminal output (thread-safe)"""
        self.terminal_output.configure(state='normal')
        self.terminal_output.insert('end', text)
        self.terminal_output.see('end')
        self.terminal_output.configure(state='disabled')
        self.root.update_idletasks()
    
    def show(self):
        """Show the window"""
        self.root.mainloop()
    
    def quit(self):
        """Quit the application"""
        self.root.quit()


def args_parser():
    parser = argparse.ArgumentParser(description='''
Configuration script for NatMEG pipeline (Tkinter version).
                                     
This script allows you to create or edit a configuration file for the NatMEG pipeline.
You can specify paths, settings, and options for various stages of the pipeline including MaxFilter,
OPM processing, and BIDS conversion. The configuration can be saved in YAML or JSON format.
You can also provide a path to an existing configuration file to load its settings.
                                     ''',
                                     add_help=True)
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    return parser.parse_args()


def config_UI(config_file: str = None):
    """Launch the configuration GUI and return the configuration"""
    window = ConfigMainWindow(config_file=config_file)
    window.show()
    
    # Return the configuration data after GUI closes
    return window.config_data


def main(config_file: str = None):
    """Main entry point"""
    args = args_parser()
    config_file = args.config or config_file
    
    window = ConfigMainWindow(config_file=config_file)
    window.show()


if __name__ == "__main__":
    main()