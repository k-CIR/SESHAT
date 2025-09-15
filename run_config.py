import yaml
import json
import sys
import os
import argparse
import re

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QCheckBox, QComboBox, QPushButton, QLabel, QGroupBox,
    QTextEdit, QScrollArea, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QProcess

default_path = '/neuro/data/local/'

class ConfigMainWindow(QMainWindow):
    """PyQt main window for NatMEG configuration editor"""
    
    def __init__(self, config_file=None):
        super().__init__()
        self.config_file = config_file
        self.config_data = {}
        self.widgets = {}  # Store widget references for data binding
        self.terminal_process = None
        self.config_saved = bool(config_file)  # True if loading existing config, False for new
        self.execute_btn = None  # Will be set in create_run_tab
        
        # Load configuration
        if self.config_file:
            self.config_data = self.load_config(self.config_file)
        else:
            self.config_data = self.create_default_config()
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("NatMEG Config Editor")
        self.setGeometry(100, 100, 900, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.create_project_tab()
        self.create_opm_tab()
        self.create_maxfilter_tab()
        self.create_bids_tab()
        self.create_run_tab()
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self.open_config)
        button_layout.addWidget(open_btn)
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config)
        button_layout.addWidget(save_btn)
        
        save_as_btn = QPushButton("Save As...")
        save_as_btn.clicked.connect(self.save_as_config)
        button_layout.addWidget(save_as_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(button_layout)
        
        # Status bar
        self.statusBar().showMessage(f"Config file: {self.config_file if self.config_file else 'None'}")
        
        # Set initial execute button state
        if self.config_saved:
            self.mark_config_saved()
        else:
            self.mark_config_changed()
    
    def create_default_config(self):
        """Create default configuration dictionary"""
        config = {
            'RUN': {
                'Copy to Cerberos': True,
                'Add HPI coregistration': True,
                'Run Maxfilter': True,
                'Run BIDS conversion': True,
                'Sync to CIR': True
            },
            'project': {
                'name': '',
                'CIR-ID': '',
                'InstitutionName': 'Karolinska Institutet',
                'InstitutionAddress': 'Nobels vag 9, 171 77, Stockholm, Sweden',
                'InstitutionDepartmentName': 'Department of Clinical Neuroscience (CNS)',
                'description': 'project for MEG data',
                'tasks': [''],
                'sinuhe_raw': '/neuro/data/sinuhe',
                'kaptah_raw': '/neuro/data/kaptah',
                'squidMEG': default_path,
                'opmMEG': default_path,
                'BIDS': default_path,
                'Calibration': '/neuro/databases/sss/sss_cal.dat',
                'Crosstalk': '/neuro/databases/ctc/ct_sparse.fif',
                'Logfile': 'pipeline_log.log'
            },
            'opm': {
                'polhemus': [''],
                'hpi_names': ['HPIpre', 'HPIpost', 'HPIbefore', 'HPIafter'],
                'frequency': 33,
                'downsample_to_hz': 1000,
                'overwrite': False,
                'plot': False,
            },
            'maxfilter': {
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
            'bids': {
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
    
    def mark_config_changed(self):
        """Mark configuration as changed and update UI accordingly"""
        self.config_saved = False
        if self.execute_btn:
            self.execute_btn.setText("Save to Execute")
            self.execute_btn.setEnabled(False)
    
    def mark_config_saved(self):
        """Mark configuration as saved and update UI accordingly"""
        self.config_saved = True
        if self.execute_btn:
            self.execute_btn.setText("Execute Pipeline")
            self.execute_btn.setEnabled(True)
    
    def create_run_form_widget(self, parent_layout, key, value):
        """Create a form widget for RUN items"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(5, 2, 5, 2)
        
        # Checkbox for the RUN item
        widget = QCheckBox(f"{key}")
        widget.setChecked(value)
        widget.stateChanged.connect(lambda state, k=key: [self.update_config_value(k, widget.isChecked()), self.mark_config_changed()])
        widget.setMinimumWidth(250)
        row_layout.addWidget(widget)
        
        row_layout.addStretch()
        
        # Store widget reference
        self.widgets[key] = widget
        
        parent_layout.addWidget(row_widget)

    def create_form_widget(self, parent_layout, key, value, help_text=None):
        """Create a form widget based on the value type"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(5, 2, 5, 2)
        
        # Label
        label = QLabel(f"{key}:")
        label.setMinimumWidth(200)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(label)
        
        # Widget based on value type
        if isinstance(value, bool):
            widget = QCheckBox()
            widget.setChecked(value)
            widget.stateChanged.connect(lambda state, k=key: [self.update_config_value(k, widget.isChecked()), self.mark_config_changed()])
        elif isinstance(value, list):
            widget = QLineEdit(', '.join(str(v) for v in value))
            widget.textChanged.connect(lambda text, k=key: [self.update_config_list(k, text), self.mark_config_changed()])
        elif key == 'trans_option':
            widget = QComboBox()
            widget.addItems(['continous', 'initial'])
            widget.setCurrentText(str(value))
            widget.currentTextChanged.connect(lambda text, k=key: [self.update_config_value(k, text), self.mark_config_changed()])
        elif key == 'maxfilter_version':
            widget = QComboBox()
            widget.addItems(['/neuro/bin/util/maxfilter', '/neuro/bin/util/mfilter'])
            widget.setCurrentText(str(value))
            widget.currentTextChanged.connect(lambda text, k=key: [self.update_config_value(k, text), self.mark_config_changed()])
        else:
            widget = QLineEdit(str(value))
            widget.textChanged.connect(lambda text, k=key: [self.update_config_value(k, text), self.mark_config_changed()])
            
            # Special handling for project name field to auto-update paths
            if key == 'name':
                widget.textChanged.connect(self.update_project_paths)
        
        row_layout.addWidget(widget)
        row_layout.addStretch()
        
        # Store widget reference
        self.widgets[key] = widget
        
        parent_layout.addWidget(row_widget)
        
        # Add help text if provided
        if help_text:
            help_label = QLabel(help_text)
            help_label.setWordWrap(True)
            help_label.setStyleSheet("color: gray; font-size: 10px; margin-left: 210px;")
            help_label.setMaximumHeight(40)
            parent_layout.addWidget(help_label)
    
    def create_scrollable_form(self, config_section, keys=None, help_texts=None):
        """Create a scrollable form for a configuration section"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(5)
        
        # Determine which keys to use
        if keys is None:
            keys = list(config_section.keys())
        
        # Create form fields
        for key in keys:
            if key in config_section:
                value = config_section[key]
                help_text = help_texts.get(key) if help_texts else None
                self.create_form_widget(form_layout, key, value, help_text)
        
        form_layout.addStretch()
        scroll_area.setWidget(form_widget)
        return scroll_area
    
    def create_project_tab(self):
        """Create the Project configuration tab"""
        project_widget = QWidget()
        project_layout = QVBoxLayout(project_widget)
        
        # Create sub-tabs for project
        project_tabs = QTabWidget()
        
        # Standard settings
        standard_keys = ['name', 'CIR-ID', 'description', 'tasks', 'sinuhe_raw', 'kaptah_raw']
        standard_help = {
            'name': 'Name of project directory on local disk',
            'CIR-ID': 'CIR ID of the project, used for data management',
            'description': 'Brief description of the project',
            'tasks': 'Comma-separated list of experimental tasks',
            'sinuhe_raw': 'Path to Sinuhe raw data directory',
            'kaptah_raw': 'Path to Kaptah raw data directory'
        }
        
        standard_form = self.create_scrollable_form(
            self.config_data['project'], 
            standard_keys, 
            standard_help
        )
        project_tabs.addTab(standard_form, "Standard Settings")
        
        # Advanced settings
        advanced_keys = [
            'InstitutionName', 'InstitutionAddress', 'InstitutionDepartmentName',
            'squidMEG', 'opmMEG', 'BIDS', 'Calibration', 'Crosstalk', 'Logfile'
        ]
        advanced_help = {
            'InstitutionName': 'Name of the institution',
            'InstitutionAddress': 'Address of the institution',
            'InstitutionDepartmentName': 'Department name',
            'squidMEG': 'Path to directory for SquidMEG data',
            'opmMEG': 'Path to directory for OPM data',
            'BIDS': 'Path to directory for BIDS data',
            'Calibration': 'Path to SSS calibration file',
            'Crosstalk': 'Path to SSS crosstalk file',
            'Logfile': 'Name of the log file'
        }
        
        advanced_form = self.create_scrollable_form(
            self.config_data['project'], 
            advanced_keys, 
            advanced_help
        )
        project_tabs.addTab(advanced_form, "Advanced Settings")
        
        project_layout.addWidget(project_tabs)
        self.tab_widget.addTab(project_widget, "Project")
    
    def create_opm_tab(self):
        """Create the OPM configuration tab"""
        opm_help = {
            'polhemus': 'Name(s) of fif-file(s) with Polhemus coregistration data',
            'hpi_names': 'Comma-separated list of names of HPI recording',
            'frequency': 'Frequency of the HPI in Hz',
            'downsample_to_hz': 'Downsample OPM data to this frequency',
            'overwrite': 'Overwrite existing OPM data files',
            'plot': 'Store a plot of the OPM data after processing'
        }
        
        opm_form = self.create_scrollable_form(self.config_data['opm'], help_texts=opm_help)
        self.tab_widget.addTab(opm_form, "OPM")
    
    def create_maxfilter_tab(self):
        """Create the MaxFilter configuration tab"""
        maxfilter_widget = QWidget()
        maxfilter_layout = QVBoxLayout(maxfilter_widget)
        
        # Create sub-tabs for maxfilter
        maxfilter_tabs = QTabWidget()
        
        # Standard settings
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
        
        standard_form = self.create_scrollable_form(
            self.config_data['maxfilter']['standard_settings'],
            help_texts=standard_help
        )
        maxfilter_tabs.addTab(standard_form, "Standard Settings")
        
        # Advanced settings
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
        
        advanced_form = self.create_scrollable_form(
            self.config_data['maxfilter']['advanced_settings'],
            help_texts=advanced_help
        )
        maxfilter_tabs.addTab(advanced_form, "Advanced Settings")
        
        maxfilter_layout.addWidget(maxfilter_tabs)
        self.tab_widget.addTab(maxfilter_widget, "MaxFilter")
    
    def create_bids_tab(self):
        """Create the BIDS configuration tab"""
        bids_widget = QWidget()
        bids_layout = QVBoxLayout(bids_widget)
        
        # Create sub-tabs for BIDS
        bids_tabs = QTabWidget()
        
        # Standard settings
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
        
        standard_form = self.create_scrollable_form(
            self.config_data['bids'],
            standard_bids_keys,
            standard_bids_help
        )
        bids_tabs.addTab(standard_form, "Standard Settings")
        
        # Dataset description
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
        
        dataset_form = self.create_scrollable_form(
            self.config_data['bids'],
            dataset_keys,
            dataset_help
        )
        bids_tabs.addTab(dataset_form, "Dataset Description")
        
        bids_layout.addWidget(bids_tabs)
        self.tab_widget.addTab(bids_widget, "BIDS")
    
    def create_run_tab(self):
        """Create the RUN configuration tab"""
        run_widget = QWidget()
        run_layout = QVBoxLayout(run_widget)
        
        # RUN settings form
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        
        for key, value in self.config_data['RUN'].items():
            self.create_run_form_widget(form_layout, key, value)
        
        form_layout.addStretch()
        run_layout.addWidget(form_widget)
        
        # Execute button
        self.execute_btn = QPushButton("Save to Execute" if not self.config_saved else "Execute Pipeline")
        self.execute_btn.setMinimumHeight(40)
        self.execute_btn.setEnabled(self.config_saved)
        self.execute_btn.clicked.connect(self.execute_pipeline)
        run_layout.addWidget(self.execute_btn)
        
        # Terminal output
        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setMinimumHeight(300)
        self.terminal_output.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Courier New', monospace, 'SF Mono', 'Monaco', 'Menlo', 'Consolas';
                font-size: 10pt;
                border: 1px solid #555555;
            }
        """)
        self.terminal_output.append("Terminal output will appear here...")
        run_layout.addWidget(self.terminal_output)
        
        self.tab_widget.addTab(run_widget, "RUN")
    
    def update_config_value(self, key, value):
        """Update configuration value"""
        # Find the correct nested location for the key
        for section in ['RUN', 'project', 'opm', 'maxfilter', 'bids']:
            if section in self.config_data:
                if key in self.config_data[section]:
                    self.config_data[section][key] = value
                    return
                elif section == 'maxfilter':
                    for subsection in ['standard_settings', 'advanced_settings']:
                        if key in self.config_data[section][subsection]:
                            self.config_data[section][subsection][key] = value
                            return
    
    def update_config_list(self, key, text):
        """Update configuration list value from comma-separated text"""
        value = [item.strip() for item in text.split(',') if item.strip()]
        self.update_config_value(key, value)
    
    def update_project_paths(self, project_name):
        """Update project-related paths when project name changes"""
        if not project_name.strip():
            return
        
        # Update paths in config
        base_path = default_path
        if project_name:
            # Update squidMEG path
            new_squid_path = f"{base_path}{project_name}/raw"
            self.config_data['project']['squidMEG'] = new_squid_path
            
            # Update opmMEG path  
            new_opm_path = f"{base_path}{project_name}/raw"
            self.config_data['project']['opmMEG'] = new_opm_path
            
            # Update BIDS path
            new_bids_path = f"{base_path}{project_name}/BIDS"
            self.config_data['project']['BIDS'] = new_bids_path
            
            # Update the widgets if they exist
            if 'squidMEG' in self.widgets:
                self.widgets['squidMEG'].setText(new_squid_path)
            if 'opmMEG' in self.widgets:
                self.widgets['opmMEG'].setText(new_opm_path)
            if 'BIDS' in self.widgets:
                self.widgets['BIDS'].setText(new_bids_path)
    
    def load_config(self, config_file=None):
        """Load configuration from file"""
        if not config_file:
            return self.create_default_config()
            
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
                return self.create_default_config()
                
            # Convert strings to lists where needed
            if config:
                if 'project' in config and 'tasks' in config['project']:
                    if isinstance(config['project']['tasks'], str):
                        config['project']['tasks'] = config['project']['tasks'].split(',')
                
            return config if config else self.create_default_config()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading config: {e}")
            return self.create_default_config()
    
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
            
            self.statusBar().showMessage(f"Config saved to: {self.config_file}")
            self.mark_config_saved()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving config: {e}")
    
    def save_as_config(self):
        """Save configuration as new file"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration File",
            default_path,
            "YAML files (*.yml *.yaml);;JSON files (*.json);;All files (*.*)"
        )
        
        if filename:
            if not filename.endswith(('.yml', '.yaml', '.json')):
                filename += '.yml'  # Default to YAML
            
            self.config_file = filename
            self.save_config()
    
    def open_config(self):
        """Open configuration file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Configuration File",
            default_path,
            "Config files (*.yml *.yaml *.json);;YAML files (*.yml *.yaml);;JSON files (*.json);;All files (*.*)"
        )
        
        if filename:
            try:
                new_config = self.load_config(filename)
                if new_config:
                    self.config_data = new_config
                    self.config_file = filename
                    self.statusBar().showMessage(f"Config loaded from: {filename}")
                    self.update_all_widgets()
                    self.mark_config_saved()  # Mark as saved since we just loaded it
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error opening config: {e}")
    
    def update_all_widgets(self):
        """Update all widgets with current config values"""
        # Update all widgets when a new config is loaded
        for key, widget in self.widgets.items():
            # Find the value in config
            value = None
            for section in ['RUN', 'project', 'opm', 'maxfilter', 'bids']:
                if section in self.config_data:
                    if key in self.config_data[section]:
                        value = self.config_data[section][key]
                        break
                    elif section == 'maxfilter':
                        for subsection in ['standard_settings', 'advanced_settings']:
                            if key in self.config_data[section][subsection]:
                                value = self.config_data[section][subsection][key]
                                break
            
            if value is not None:
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(str(value))
                elif isinstance(widget, QLineEdit):
                    if isinstance(value, list):
                        widget.setText(', '.join(str(v) for v in value))
                    else:
                        widget.setText(str(value))
    
    def execute_pipeline(self):
        """Execute the pipeline"""
        self.terminal_output.clear()
        self.terminal_output.append("Executing pipeline...")
        
        # Build command
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pipeline_path = os.path.join(base_dir, 'natmeg_pipeline.py')
        
        if not os.path.exists(pipeline_path):
            self.terminal_output.append("Error: natmeg_pipeline.py not found!")
            return
        
        cmd = [sys.executable, '-u', pipeline_path, 'run']
        if self.config_file:
            cmd += ['--config', self.config_file]
        
        # Start process
        self.terminal_process = QProcess(self)
        self.terminal_process.readyReadStandardOutput.connect(self.handle_stdout)
        self.terminal_process.readyReadStandardError.connect(self.handle_stderr)
        self.terminal_process.finished.connect(self.process_finished)
        
        self.terminal_process.start(sys.executable, cmd[1:])
        
        if not self.terminal_process.waitForStarted():
            self.terminal_output.append("Failed to start pipeline process!")
    
    def handle_stdout(self):
        """Handle stdout from subprocess"""
        data = self.terminal_process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8")
        self.terminal_output.append(stdout.strip())
        self.terminal_output.ensureCursorVisible()
    
    def handle_stderr(self):
        """Handle stderr from subprocess"""
        data = self.terminal_process.readAllStandardError()
        stderr = bytes(data).decode("utf8")
        self.terminal_output.append(f"ERROR: {stderr.strip()}")
        self.terminal_output.ensureCursorVisible()
    
    def process_finished(self):
        """Handle process completion"""
        exit_code = self.terminal_process.exitCode()
        self.terminal_output.append(f"\nProcess finished with exit code: {exit_code}")


def args_parser():
    parser = argparse.ArgumentParser(description='''
Configuration script for NatMEG pipeline (PyQt version).
                                     
This script allows you to create or edit a configuration file for the NatMEG pipeline.
You can specify paths, settings, and options for various stages of the pipeline including MaxFilter,
OPM processing, and BIDS conversion. The configuration can be saved in YAML or JSON format.
You can also provide a path to an existing configuration file to load its settings.
                                     ''',
                                     add_help=True)
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    return parser.parse_args()


def main(config_file: str = None):
    """Main entry point"""
    args = args_parser()
    config_file = args.config or config_file
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for better cross-platform appearance
    
    # Set application properties
    app.setApplicationName("NatMEG Config Editor")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("NatMEG")
    
    window = ConfigMainWindow(config_file=config_file)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()