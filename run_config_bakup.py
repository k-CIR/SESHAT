import yaml
import json
import sys
import os
from os.path import exists
import argparse
import threading
import subprocess
import queue
import re

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QLabel, QLineEdit, 
                             QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox,
                             QPushButton, QTextEdit, QFileDialog, QMessageBox,
                             QScrollArea, QFrame, QGroupBox, QGridLayout,
                             QSplitter, QProgressBar, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

default_path = '/neuro/data/local/'

def create_default_config():
    return {
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
                'maxfilter_version': '/neuro/bin/util/maxfilter',
                'Temporal signal space separation (tSSS)': True,
                'Movement compensation': True,
                'HPI correlations limit': 0.9,
                'overwrite': False,
                'buffer_size_sec': 10.0,
                'skip_maxfilter': False,
                'origin': [0, 0, 40]  # default origin
            },
            'advanced_settings': {
                'head_position_estimation': True,
                'head_position_file': '',
                'correlation': '',
                'Temporal signal space separation (tSSS)': {
                    'temporal_window_sec': 10.0,
                    'head_position_continous_hpi': True
                },
                'Movement compensation': {
                    'head_position_file': '',
                    'average_head_position': True
                }
            }
        },
        'bids': {
            'validate': True,
            'dataset_description': {
                'Name': '',
                'Authors': [''],
                'ReferencesAndLinks': [''],
                'BIDSVersion': '1.7.0',
                'License': 'CC0',
                'HowToAcknowledge': ''
            },
            'participants': {
                'age': '',
                'sex': 'n/a',
                'handedness': 'n/a'
            }
        }
    }


class WorkerThread(QThread):
    """Thread for running the pipeline without blocking the GUI"""
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        
    def run(self):
        try:
            # This would run the actual pipeline
            # For now, just simulate the process
            self.output_signal.emit("Starting NatMEG pipeline...")
            self.output_signal.emit("Configuration loaded successfully")
            
            if self.config['RUN'].get('Copy to Cerberos'):
                self.output_signal.emit("Step 1: Copying to Cerberos...")
                
            if self.config['RUN'].get('Add HPI coregistration'):
                self.output_signal.emit("Step 2: Adding HPI coregistration...")
                
            if self.config['RUN'].get('Run Maxfilter'):
                self.output_signal.emit("Step 3: Running MaxFilter...")
                
            if self.config['RUN'].get('Run BIDS conversion'):
                self.output_signal.emit("Step 4: Converting to BIDS...")
                
            if self.config['RUN'].get('Sync to CIR'):
                self.output_signal.emit("Step 5: Syncing to CIR...")
                
            self.output_signal.emit("Pipeline completed successfully!")
            self.finished_signal.emit()
            
        except Exception as e:
            self.error_signal.emit(str(e))


class ConfigEditor(QMainWindow):
    def __init__(self, config_file=None):
        super().__init__()
        self.config_file = config_file
        self.config = {}
        self.widgets = {}  # Store references to widgets for updating
        
        self.setWindowTitle("NatMEG Config Editor")
        self.setGeometry(100, 100, 800, 900)
        
        # Load config
        if config_file and exists(config_file):
            self.load_config_file(config_file)
        else:
            self.config = create_default_config()
            
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.create_run_tab()
        self.create_project_tab()
        self.create_opm_tab()
        self.create_maxfilter_tab()
        self.create_bids_tab()
        
        # Create button panel
        self.create_button_panel(layout)
        
        # Create output panel
        self.create_output_panel(layout)
        
    def create_menu_bar(self):
        """Create the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        # New config
        new_action = file_menu.addAction('New Config')
        new_action.triggered.connect(self.new_config)
        
        # Load config
        load_action = file_menu.addAction('Load Config...')
        load_action.triggered.connect(self.load_config)
        
        # Save config
        save_action = file_menu.addAction('Save Config')
        save_action.triggered.connect(self.save_config)
        
        # Save config as
        save_as_action = file_menu.addAction('Save Config As...')
        save_as_action.triggered.connect(self.save_config_as)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)
        
    def create_run_tab(self):
        """Create the Run tab"""
        tab = QWidget()
        self.tab_widget.addTab(tab, "Run")
        
        layout = QVBoxLayout()
        tab.setLayout(layout)
        
        # Run options group
        run_group = QGroupBox("Pipeline Steps")
        run_layout = QVBoxLayout()
        run_group.setLayout(run_layout)
        
        run_options = [
            ('Copy to Cerberos', 'Copy to Cerberos'),
            ('Add HPI coregistration', 'Add HPI coregistration'),
            ('Run Maxfilter', 'Run Maxfilter'),
            ('Run BIDS conversion', 'Run BIDS conversion'),
            ('Sync to CIR', 'Sync to CIR')
        ]
        
        for key, label in run_options:
            checkbox = QCheckBox(label)
            checkbox.setChecked(self.config['RUN'].get(key, True))
            checkbox.stateChanged.connect(lambda state, k=key: self.update_run_config(k, state == Qt.Checked))
            run_layout.addWidget(checkbox)
            self.widgets[f'run_{key}'] = checkbox
            
        layout.addWidget(run_group)
        layout.addStretch()
        
    def create_project_tab(self):
        """Create the Project tab"""
        tab = QWidget()
        self.tab_widget.addTab(tab, "Project")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)
        tab_layout.addWidget(scroll)
        
        scroll_widget = QWidget()
        scroll.setWidget(scroll_widget)
        layout = QVBoxLayout()
        scroll_widget.setLayout(layout)
        
        # Project info group
        info_group = QGroupBox("Project Information")
        info_layout = QGridLayout()
        info_group.setLayout(info_layout)
        
        project_fields = [
            ('name', 'Project Name:', QLineEdit),
            ('CIR-ID', 'CIR ID:', QLineEdit),
            ('InstitutionName', 'Institution Name:', QLineEdit),
            ('InstitutionAddress', 'Institution Address:', QLineEdit),
            ('InstitutionDepartmentName', 'Department:', QLineEdit),
            ('description', 'Description:', QLineEdit)
        ]
        
        for i, (key, label, widget_class) in enumerate(project_fields):
            info_layout.addWidget(QLabel(label), i, 0)
            widget = widget_class()
            widget.setText(str(self.config['project'].get(key, '')))
            widget.textChanged.connect(lambda text, k=key: self.update_project_config(k, text))
            info_layout.addWidget(widget, i, 1)
            self.widgets[f'project_{key}'] = widget
            
        layout.addWidget(info_group)
        
        # Paths group
        paths_group = QGroupBox("Data Paths")
        paths_layout = QGridLayout()
        paths_group.setLayout(paths_layout)
        
        path_fields = [
            ('sinuhe_raw', 'Sinuhe Raw:', '/neuro/data/sinuhe'),
            ('kaptah_raw', 'Kaptah Raw:', '/neuro/data/kaptah'),
            ('squidMEG', 'SquidMEG:', default_path),
            ('opmMEG', 'OPM MEG:', default_path),
            ('BIDS', 'BIDS:', default_path),
            ('Calibration', 'Calibration:', '/neuro/databases/sss/sss_cal.dat'),
            ('Crosstalk', 'Crosstalk:', '/neuro/databases/ctc/ct_sparse.fif'),
            ('Logfile', 'Log File:', 'pipeline_log.log')
        ]
        
        for i, (key, label, default) in enumerate(path_fields):
            paths_layout.addWidget(QLabel(label), i, 0)
            
            path_widget = QLineEdit()
            path_widget.setText(str(self.config['project'].get(key, default)))
            path_widget.textChanged.connect(lambda text, k=key: self.update_project_config(k, text))
            paths_layout.addWidget(path_widget, i, 1)
            
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda checked, k=key, w=path_widget: self.browse_path(k, w))
            paths_layout.addWidget(browse_btn, i, 2)
            
            self.widgets[f'project_{key}'] = path_widget
            
        layout.addWidget(paths_group)
        layout.addStretch()
        
    def create_opm_tab(self):
        """Create the OPM tab"""
        tab = QWidget()
        self.tab_widget.addTab(tab, "OPM")
        
        layout = QVBoxLayout()
        tab.setLayout(layout)
        
        # OPM settings group
        opm_group = QGroupBox("OPM Settings")
        opm_layout = QGridLayout()
        opm_group.setLayout(opm_layout)
        
        # Frequency
        opm_layout.addWidget(QLabel("Frequency:"), 0, 0)
        freq_spin = QSpinBox()
        freq_spin.setRange(1, 1000)
        freq_spin.setValue(self.config['opm'].get('frequency', 33))
        freq_spin.valueChanged.connect(lambda value: self.update_opm_config('frequency', value))
        opm_layout.addWidget(freq_spin, 0, 1)
        self.widgets['opm_frequency'] = freq_spin
        
        # Downsample
        opm_layout.addWidget(QLabel("Downsample to Hz:"), 1, 0)
        downsample_spin = QSpinBox()
        downsample_spin.setRange(100, 10000)
        downsample_spin.setValue(self.config['opm'].get('downsample_to_hz', 1000))
        downsample_spin.valueChanged.connect(lambda value: self.update_opm_config('downsample_to_hz', value))
        opm_layout.addWidget(downsample_spin, 1, 1)
        self.widgets['opm_downsample'] = downsample_spin
        
        # Checkboxes
        overwrite_cb = QCheckBox("Overwrite")
        overwrite_cb.setChecked(self.config['opm'].get('overwrite', False))
        overwrite_cb.stateChanged.connect(lambda state: self.update_opm_config('overwrite', state == Qt.Checked))
        opm_layout.addWidget(overwrite_cb, 2, 0)
        self.widgets['opm_overwrite'] = overwrite_cb
        
        plot_cb = QCheckBox("Plot")
        plot_cb.setChecked(self.config['opm'].get('plot', False))
        plot_cb.stateChanged.connect(lambda state: self.update_opm_config('plot', state == Qt.Checked))
        opm_layout.addWidget(plot_cb, 2, 1)
        self.widgets['opm_plot'] = plot_cb
        
        layout.addWidget(opm_group)
        layout.addStretch()
        
    def create_maxfilter_tab(self):
        """Create the MaxFilter tab"""
        tab = QWidget()
        self.tab_widget.addTab(tab, "MaxFilter")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)
        tab_layout.addWidget(scroll)
        
        scroll_widget = QWidget()
        scroll.setWidget(scroll_widget)
        layout = QVBoxLayout()
        scroll_widget.setLayout(layout)
        
        # Standard settings
        std_group = QGroupBox("Standard Settings")
        std_layout = QGridLayout()
        std_group.setLayout(std_layout)
        
        # MaxFilter version path
        std_layout.addWidget(QLabel("MaxFilter Path:"), 0, 0)
        mf_path = QLineEdit()
        mf_path.setText(self.config['maxfilter']['standard_settings'].get('maxfilter_version', '/neuro/bin/util/maxfilter'))
        mf_path.textChanged.connect(lambda text: self.update_maxfilter_config('standard_settings', 'maxfilter_version', text))
        std_layout.addWidget(mf_path, 0, 1)
        self.widgets['mf_path'] = mf_path
        
        # Checkboxes
        tsss_cb = QCheckBox("Temporal SSS")
        tsss_cb.setChecked(self.config['maxfilter']['standard_settings'].get('Temporal signal space separation (tSSS)', True))
        tsss_cb.stateChanged.connect(lambda state: self.update_maxfilter_config('standard_settings', 'Temporal signal space separation (tSSS)', state == Qt.Checked))
        std_layout.addWidget(tsss_cb, 1, 0)
        self.widgets['mf_tsss'] = tsss_cb
        
        movement_cb = QCheckBox("Movement Compensation")
        movement_cb.setChecked(self.config['maxfilter']['standard_settings'].get('Movement compensation', True))
        movement_cb.stateChanged.connect(lambda state: self.update_maxfilter_config('standard_settings', 'Movement compensation', state == Qt.Checked))
        std_layout.addWidget(movement_cb, 1, 1)
        self.widgets['mf_movement'] = movement_cb
        
        # HPI correlation limit
        std_layout.addWidget(QLabel("HPI Correlation Limit:"), 2, 0)
        hpi_spin = QDoubleSpinBox()
        hpi_spin.setRange(0.0, 1.0)
        hpi_spin.setSingleStep(0.1)
        hpi_spin.setValue(self.config['maxfilter']['standard_settings'].get('HPI correlations limit', 0.9))
        hpi_spin.valueChanged.connect(lambda value: self.update_maxfilter_config('standard_settings', 'HPI correlations limit', value))
        std_layout.addWidget(hpi_spin, 2, 1)
        self.widgets['mf_hpi_corr'] = hpi_spin
        
        layout.addWidget(std_group)
        layout.addStretch()
        
    def create_bids_tab(self):
        """Create the BIDS tab"""
        tab = QWidget()
        self.tab_widget.addTab(tab, "BIDS")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)
        tab_layout.addWidget(scroll)
        
        scroll_widget = QWidget()
        scroll.setWidget(scroll_widget)
        layout = QVBoxLayout()
        scroll_widget.setLayout(layout)
        
        # Validation
        validate_cb = QCheckBox("Validate BIDS")
        validate_cb.setChecked(self.config['bids'].get('validate', True))
        validate_cb.stateChanged.connect(lambda state: self.update_bids_config('validate', state == Qt.Checked))
        layout.addWidget(validate_cb)
        self.widgets['bids_validate'] = validate_cb
        
        # Dataset description
        desc_group = QGroupBox("Dataset Description")
        desc_layout = QGridLayout()
        desc_group.setLayout(desc_layout)
        
        desc_fields = [
            ('Name', 'Dataset Name:', QLineEdit),
            ('BIDSVersion', 'BIDS Version:', QLineEdit),
            ('License', 'License:', QLineEdit),
            ('HowToAcknowledge', 'How to Acknowledge:', QLineEdit)
        ]
        
        for i, (key, label, widget_class) in enumerate(desc_fields):
            desc_layout.addWidget(QLabel(label), i, 0)
            widget = widget_class()
            widget.setText(str(self.config['bids']['dataset_description'].get(key, '')))
            widget.textChanged.connect(lambda text, k=key: self.update_bids_dataset_config(k, text))
            desc_layout.addWidget(widget, i, 1)
            self.widgets[f'bids_desc_{key}'] = widget
            
        layout.addWidget(desc_group)
        layout.addStretch()
        
    def create_button_panel(self, parent_layout):
        """Create the button panel"""
        button_layout = QHBoxLayout()
        
        # Run button
        self.run_button = QPushButton("Run Pipeline")
        self.run_button.clicked.connect(self.run_pipeline)
        button_layout.addWidget(self.run_button)
        
        # Stop button
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_pipeline)
        button_layout.addWidget(self.stop_button)
        
        button_layout.addStretch()
        
        # Save button
        save_button = QPushButton("Save Config")
        save_button.clicked.connect(self.save_config)
        button_layout.addWidget(save_button)
        
        parent_layout.addLayout(button_layout)
        
    def create_output_panel(self, parent_layout):
        """Create the output panel"""
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        output_group.setLayout(output_layout)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(200)
        output_layout.addWidget(self.output_text)
        
        parent_layout.addWidget(output_group)
        
    def browse_path(self, key, widget):
        """Browse for a path"""
        if 'file' in key.lower() or key in ['Calibration', 'Crosstalk', 'Logfile']:
            path, _ = QFileDialog.getOpenFileName(self, f"Select {key}", "", "All Files (*)")
        else:
            path = QFileDialog.getExistingDirectory(self, f"Select {key} Directory")
            
        if path:
            widget.setText(path)
            
    def update_run_config(self, key, value):
        """Update run configuration"""
        self.config['RUN'][key] = value
        
    def update_project_config(self, key, value):
        """Update project configuration"""
        self.config['project'][key] = value
        
    def update_opm_config(self, key, value):
        """Update OPM configuration"""
        self.config['opm'][key] = value
        
    def update_maxfilter_config(self, section, key, value):
        """Update MaxFilter configuration"""
        if section not in self.config['maxfilter']:
            self.config['maxfilter'][section] = {}
        self.config['maxfilter'][section][key] = value
        
    def update_bids_config(self, key, value):
        """Update BIDS configuration"""
        self.config['bids'][key] = value
        
    def update_bids_dataset_config(self, key, value):
        """Update BIDS dataset configuration"""
        self.config['bids']['dataset_description'][key] = value
        
    def new_config(self):
        """Create a new configuration"""
        self.config = create_default_config()
        self.config_file = None
        self.update_widgets_from_config()
        self.setWindowTitle("NatMEG Config Editor - New Config")
        
    def load_config(self):
        """Load configuration from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Load Configuration", 
            "", 
            "YAML Files (*.yml *.yaml);;JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.load_config_file(file_path)
            
    def load_config_file(self, file_path):
        """Load configuration from a specific file"""
        try:
            with open(file_path, 'r') as f:
                if file_path.endswith(('.yml', '.yaml')):
                    self.config = yaml.safe_load(f)
                else:
                    self.config = json.load(f)
                    
            self.config_file = file_path
            self.update_widgets_from_config()
            self.setWindowTitle(f"NatMEG Config Editor - {os.path.basename(file_path)}")
            self.output_text.append(f"Loaded configuration from {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load configuration:\n{e}")
            
    def save_config(self):
        """Save configuration"""
        if self.config_file:
            self.save_config_to_file(self.config_file)
        else:
            self.save_config_as()
            
    def save_config_as(self):
        """Save configuration as new file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration",
            "",
            "YAML Files (*.yml);;JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.save_config_to_file(file_path)
            
    def save_config_to_file(self, file_path):
        """Save configuration to a specific file"""
        try:
            with open(file_path, 'w') as f:
                if file_path.endswith(('.yml', '.yaml')):
                    yaml.dump(self.config, f, default_flow_style=False, indent=2)
                else:
                    json.dump(self.config, f, indent=2)
                    
            self.config_file = file_path
            self.setWindowTitle(f"NatMEG Config Editor - {os.path.basename(file_path)}")
            self.output_text.append(f"Saved configuration to {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration:\n{e}")
            
    def update_widgets_from_config(self):
        """Update all widgets from the current configuration"""
        # This would update all widgets based on the loaded config
        # Implementation depends on the specific widget structure
        pass
        
    def run_pipeline(self):
        """Run the pipeline"""
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.output_text.clear()
        
        # Create and start worker thread
        self.worker = WorkerThread(self.config)
        self.worker.output_signal.connect(self.output_text.append)
        self.worker.finished_signal.connect(self.on_pipeline_finished)
        self.worker.error_signal.connect(self.on_pipeline_error)
        self.worker.start()
        
    def stop_pipeline(self):
        """Stop the pipeline"""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.on_pipeline_finished()
        
    def on_pipeline_finished(self):
        """Handle pipeline completion"""
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.output_text.append("Pipeline execution completed.")
        
    def on_pipeline_error(self, error_msg):
        """Handle pipeline errors"""
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        QMessageBox.critical(self, "Pipeline Error", f"An error occurred:\n{error_msg}")


def main(config_file=None):
    """Main function"""
    app = QApplication(sys.argv)
    
    editor = ConfigEditor(config_file)
    editor.show()
    
    sys.exit(app.exec_())


def args_parser():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='NatMEG Configuration Editor')
    parser.add_argument('--config', help='Configuration file to load')
    return parser.parse_args()


if __name__ == "__main__":
    args = args_parser()
    main(args.config)
