import sys
import os
import argparse
import re
import json
import yaml

from PySide6.QtCore import Qt, QTimer, QProcess, QProcessEnvironment
from PySide6.QtGui import QIcon, QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QScrollArea, QLabel, QLineEdit, QCheckBox, QComboBox,
    QGroupBox, QProgressBar, QPlainTextEdit, QPushButton, QFileDialog,
    QMessageBox,
)

from seshat.utils import apply_ansi_colors_to_qt, PIPELINE_STAGES, _PROGRESS_SENTINEL
from seshat.config import (
    create_default_config,
    merge_with_defaults,
    rename_legacy_keys,
    default_path,
    RUN_LABELS,
)

# Minimal status glyphs for pipeline stage rows in the RUN tab.
#
# Font compatibility notes (both bugs observed on Rocky Linux under Tk;
# kept unchanged here pending re-verification under Qt on the same target
# — Qt's own font shaping may render the wider glyph set fine, but do not
# assume that without testing on the real Rocky Linux workstation):
#  - '\u25cb' (○) and '\u25cf' (●) render correctly there — confirmed safe.
#  - '\u25d0' (◐) and '\u2713'/'\u2715' (✓/✕) render as blank/tofu boxes
#    under Tk — they sit outside the small Geometric Shapes subset those
#    fonts actually cover. No glyph here may be assumed safe unless it is
#    one of the two already confirmed, or plain ASCII.
#  - 'done' reuses '\u25cf' (●) like 'running' does, distinguished by color
#    alone. 'error' uses ASCII 'X' rather than '\u2715' for the same reason.
STAGE_STATUS_ICONS = {
    'waiting': ('\u25cb', 'gray'),      # ○ static — confirmed safe
    'running': ('\u25cf', '#d93025'),   # ● blinking red (REC light) — confirmed safe
    'done':    ('\u25cf', '#188038'),   # ● solid green — confirmed safe
    'error':   ('\u0058', '#d93025'),   # X solid red — plain ASCII, always safe
    'warning': ('\u0021', 'orange'),    # ! solid orange — plain ASCII, always safe
}

# Blink period (ms) for the 'running' REC-light effect.
_BLINK_INTERVAL_MS = 500


class ConfigMainWindow(QMainWindow):
    """PySide6 main window for SESHAT configuration editor"""

    def __init__(self, config_file=None):
        super().__init__()
        self.setWindowTitle(
            "SESHAT - Scripts for Extraction, Synchronisation, HPI + Analog alignment and Transfer"
        )
        self.resize(900, 800)
        self.logo_pixmap = None

        self._setup_branding_assets()

        self.config_file = config_file
        self.config_data = {}
        self.widgets = {}
        self.manual_edits = set()
        self.programmatic_update = False
        self._last_project_name = ''
        self._last_root_path = ''
        self.terminal_process = None  # QProcess instance while a run is active
        self._stdout_buffer = ''
        self.config_saved = bool(config_file)
        self.execute_btn = None
        self.abort_btn = None
        self.stage_status_labels = {}
        self._last_running_stage = None

        # 'running' REC-light blink state: which stage/label/icon/color are
        # currently blinking, and a repeating QTimer driving the toggle.
        self._blink_stage = None
        self._blink_label = None
        self._blink_icon = ''
        self._blink_color = 'black'
        self._blink_on = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(_BLINK_INTERVAL_MS)
        self._blink_timer.timeout.connect(self._blink_tick)

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
                icon = QIcon(candidate)
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    self.logo_pixmap = icon.pixmap(96, 96)
                    self.logo_path = candidate
                    break

    def init_ui(self):
        """Initialize the user interface"""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(2, 5, 2, 5)

        if self.logo_pixmap is not None:
            logo_label = QLabel()
            logo_label.setPixmap(self.logo_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            main_layout.addWidget(logo_label)

        self.notebook = QTabWidget()
        main_layout.addWidget(self.notebook, 1)

        self.create_project_tab()
        self.create_opm_tab()
        # self.create_maxfilter_tab()
        # self.create_bids_tab()
        self.create_run_tab()

        button_frame = QWidget()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(4, 10, 4, 0)
        button_layout.addStretch(1)

        # Original Tk code packed Cancel/Save/Save As/Open with side='right'
        # in that order, which visually renders left-to-right as:
        # Open, Save As..., Save, Cancel. Reproduce that order here.
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self.open_config)
        save_as_btn = QPushButton("Save As...")
        save_as_btn.clicked.connect(self.save_as_config)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.quit)

        for btn in (open_btn, save_as_btn, save_btn, cancel_btn):
            button_layout.addWidget(btn)

        main_layout.addWidget(button_frame)

        self.status_label = QLabel(f"Config file: {self.config_file if self.config_file else 'None'}")
        main_layout.addWidget(self.status_label)

        if self.config_saved:
            self.mark_config_saved()
        else:
            self.mark_config_changed()

    def create_scrollable_frame(self, parent_widget):
        """Create a scrollable area inside `parent_widget` (a bare QWidget
        tab page with no layout yet) and return the QVBoxLayout that child
        rows should be added to via addWidget(). Caller must add a trailing
        addStretch(1) once all rows are added, to keep rows top-aligned."""
        outer_layout = QVBoxLayout(parent_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(1)
        scroll.setWidget(content)

        return content_layout

    @staticmethod
    def _get_widget_value(widget):
        """Read the current value out of a form widget, mirroring what
        Tk's `widget.var.get()` used to return."""
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QLineEdit):
            return widget.text()
        return None

    @staticmethod
    def _set_widget_value(widget, value):
        """Write a value into a form widget, mirroring what Tk's
        `widget.var.set(value)` used to do. Note: like Tk's StringVar/
        BooleanVar, this fires the widget's change signal synchronously;
        callers relying on that during programmatic updates must guard
        with self.programmatic_update the same way the original code did."""
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(str(value))
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))

    def create_form_widget(self, layout, key, value, help_text=None):
        """Create a form widget based on the value type"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 1, 2, 1)

        label = QLabel(f"{key}:")
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setFixedWidth(170)
        row_layout.addWidget(label)

        if isinstance(value, bool):
            widget = QCheckBox()
            widget.setChecked(value)
            widget.stateChanged.connect(lambda _state, k=key, w=widget: (
                self.update_config_value(k, w.isChecked()), self.mark_config_changed()))
        elif isinstance(value, list):
            widget = QLineEdit(', '.join(str(v) for v in value))
            widget.textChanged.connect(lambda text, k=key: (
                self.update_config_list(k, text), self.mark_config_changed()))
        elif key == 'trans_option':
            widget = QComboBox()
            widget.setEditable(True)
            widget.addItems(['continuous', 'initial'])
            widget.setCurrentText(str(value))
            widget.currentTextChanged.connect(lambda text, k=key: (
                self.update_config_value(k, text), self.mark_config_changed()))
        elif key == 'maxfilter_version':
            widget = QComboBox()
            widget.setEditable(True)
            widget.addItems(['/neuro/bin/util/maxfilter', '/neuro/bin/util/mfilter'])
            widget.setCurrentText(str(value))
            widget.currentTextChanged.connect(lambda text, k=key: (
                self.update_config_value(k, text), self.mark_config_changed()))
        else:
            widget = QLineEdit(str(value))
            if key == 'Name':
                def update_name_and_paths(text):
                    self.update_config_value(key, text)
                    self.mark_config_changed()
                    self.update_project_paths()
                widget.textChanged.connect(update_name_and_paths)
            elif key == 'Root':
                def update_root_and_paths(text):
                    self.update_config_value(key, text)
                    self.mark_config_changed()
                    self.update_project_paths()
                widget.textChanged.connect(update_root_and_paths)
            elif key in ['Raw', 'BIDS', 'Calibration', 'Crosstalk']:
                # Single consolidated callback guarded by programmatic_update
                # to avoid spurious updates when update_project_paths sets
                # these widgets.
                def make_path_callback(field_key):
                    def cb(text):
                        if self.programmatic_update:
                            return
                        self.update_config_value(field_key, text)
                        self.mark_config_changed()
                        self.mark_manual_edit(field_key)
                    return cb
                widget.textChanged.connect(make_path_callback(key))
            else:
                widget.textChanged.connect(lambda text, k=key: (
                    self.update_config_value(k, text), self.mark_config_changed()))

        row_layout.addWidget(widget, 1)
        self.widgets[key] = widget
        layout.addWidget(row)

        if help_text:
            help_row = QWidget()
            help_layout = QHBoxLayout(help_row)
            help_layout.setContentsMargins(170, 0, 2, 2)
            help_label = QLabel(help_text)
            help_label.setStyleSheet("color: gray;")
            help_font = QFont()
            help_font.setPointSize(8)
            help_label.setFont(help_font)
            help_layout.addWidget(help_label)
            layout.addWidget(help_row)

    def create_run_form_widget(self, layout, key, value):
        """Create a form widget for RUN items using human-readable labels"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 1, 0, 1)

        label = RUN_LABELS.get(key, key)
        widget = QCheckBox(label)
        widget.setChecked(bool(value))
        widget.stateChanged.connect(lambda _state, k=key, w=widget: (
            self.update_config_value(k, w.isChecked()), self.mark_config_changed()))
        row_layout.addWidget(widget)
        self.widgets[key] = widget

        status_label = QLabel('')
        status_label.setFixedWidth(20)
        status_font = QFont('Monospace')
        status_font.setPointSize(11)
        status_label.setFont(status_font)
        row_layout.addWidget(status_label)
        row_layout.addStretch(1)
        self.stage_status_labels[key] = status_label

        layout.addWidget(row)

    def create_stage_status_row(self, layout, key, label_text):
        """Create a plain (non-checkbox) status row for pipeline stages that
        have no corresponding RUN config entry (currently only 'report',
        which always runs unless --no-report, never passed by the GUI)."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 1, 0, 1)

        row_layout.addWidget(QLabel(label_text))

        status_label = QLabel('')
        status_label.setFixedWidth(20)
        status_font = QFont('Monospace')
        status_font.setPointSize(11)
        status_label.setFont(status_font)
        row_layout.addWidget(status_label)
        row_layout.addStretch(1)
        self.stage_status_labels[key] = status_label

        layout.addWidget(row)

    def create_project_tab(self):
        """Create the Project configuration tab"""
        project_tab = QWidget()
        self.notebook.addTab(project_tab, "Project")
        project_tab_layout = QVBoxLayout(project_tab)
        project_tab_layout.setContentsMargins(2, 2, 2, 2)

        project_notebook = QTabWidget()
        project_tab_layout.addWidget(project_notebook)

        standard_tab = QWidget()
        project_notebook.addTab(standard_tab, "Standard Settings")
        standard_scrollable = self.create_scrollable_frame(standard_tab)

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
        standard_scrollable.addStretch(1)

        advanced_tab = QWidget()
        project_notebook.addTab(advanced_tab, "Advanced Settings")
        advanced_scrollable = self.create_scrollable_frame(advanced_tab)

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
        advanced_scrollable.addStretch(1)

    def create_opm_tab(self):
        """Create the OPM configuration tab"""
        opm_tab = QWidget()
        self.notebook.addTab(opm_tab, "OPM")
        opm_scrollable = self.create_scrollable_frame(opm_tab)

        opm_help = {
            'rename_analog_channels': 'Rename analog channels using a mapping file',
            'polhemus':       'Name(s) of fif-file(s) with Polhemus coregistration data',
            'hpi_names':      'Comma-separated list of names of HPI recording',
            'frequency':      'Frequency of the HPI in Hz',
            'gof_limit':      'Minimum dipole GOF for an HPI coil to be included in the device-to-head transform fit',
            'center_matching': 'Centroid-centre HPI/Polhemus point clouds before nearest-neighbour matching (uncheck to reproduce legacy uncentred matching; regression-testing only)',
            'downsample_to_hz': 'Downsample OPM data to this frequency',
            'noise_reffile':  'Path to a reference recording (e.g. empty room/resting state) for channel noise detection; a 10s window starting 10s after its start is used',
            'overwrite':      'Overwrite existing OPM data files',
            'plot':           'Store a plot of the OPM data after processing',
        }

        for key, value in self.config_data['OPM'].items():
            help_text = opm_help.get(key)
            self.create_form_widget(opm_scrollable, key, value, help_text)
        opm_scrollable.addStretch(1)

    def create_run_tab(self):
        """Create the RUN configuration tab"""
        run_tab = QWidget()
        self.notebook.addTab(run_tab, "RUN")
        run_layout = QVBoxLayout(run_tab)

        run_settings_group = QGroupBox("Pipeline Steps")
        run_settings_layout = QVBoxLayout(run_settings_group)
        run_layout.addWidget(run_settings_group)

        # Iterate the shared PIPELINE_STAGES registry (instead of just
        # self.config_data['RUN'].items()) so 'report' also gets a status
        # row, even though it isn't a user-toggleable RUN key.
        for key, label_text in PIPELINE_STAGES:
            if key in self.config_data['RUN']:
                self.create_run_form_widget(run_settings_layout, key, self.config_data['RUN'][key])
            else:
                self.create_stage_status_row(run_settings_layout, key, label_text)

        execute_frame = QWidget()
        execute_layout = QHBoxLayout(execute_frame)
        execute_layout.setContentsMargins(0, 0, 0, 0)
        run_layout.addWidget(execute_frame)

        self.execute_btn = QPushButton(
            "Execute Pipeline" if self.config_saved else "Save to Execute"
        )
        self.execute_btn.clicked.connect(self.execute_pipeline)
        self.execute_btn.setEnabled(self.config_saved)
        execute_layout.addWidget(self.execute_btn)

        self.abort_btn = QPushButton("Abort")
        self.abort_btn.clicked.connect(self.abort_pipeline)
        self.abort_btn.setEnabled(False)
        execute_layout.addWidget(self.abort_btn)
        execute_layout.addStretch(1)

        progress_frame = QWidget()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(0, 5, 0, 0)
        run_layout.addWidget(progress_frame)

        self.progress_label = QLabel("Ready")
        progress_font = QFont()
        progress_font.setPointSize(9)
        self.progress_label.setFont(progress_font)
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        terminal_group = QGroupBox("Terminal Output")
        terminal_layout = QVBoxLayout(terminal_group)
        run_layout.addWidget(terminal_group, 1)

        self.terminal_output = QPlainTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setStyleSheet(
            "background-color: black; color: white; selection-background-color: #4d4d4d;"
        )
        terminal_font = QFont('Courier')
        terminal_font.setPointSize(10)
        self.terminal_output.setFont(terminal_font)
        terminal_layout.addWidget(self.terminal_output)

        self.terminal_output.setPlainText("Terminal output will appear here...\n")

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
                    self._set_widget_value(self.widgets[field], new_path)

            if self.config_data['Project'].get('Root', '') != root_path:
                self.config_data['Project']['Root'] = root_path
                if 'Root' in self.widgets:
                    self._set_widget_value(self.widgets['Root'], root_path)

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
            self.execute_btn.setText("Save to Execute")
            self.execute_btn.setEnabled(False)
        if self.abort_btn:
            self.abort_btn.setEnabled(False)

    def mark_config_saved(self):
        """Mark configuration as saved and update UI accordingly"""
        self.config_saved = True
        if self.execute_btn:
            self.execute_btn.setText("Execute Pipeline")
            self.execute_btn.setEnabled(True)
        if self.abort_btn:
            self.abort_btn.setEnabled(False)

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
                config = merge_with_defaults(config, create_default_config())

            return config if config else create_default_config()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading config: {e}")
            return create_default_config()

    def save_config(self):
        """Save current configuration"""
        if not self.config_file:
            self.save_as_config()
            return

        if os.path.exists(self.config_file):
            response = QMessageBox.question(
                self,
                "Overwrite File?",
                f"The file '{os.path.basename(self.config_file)}' already exists.\n\n"
                f"Do you want to overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return

        try:
            if self.config_file.endswith('.yml') or self.config_file.endswith('.yaml'):
                with open(self.config_file, 'w') as file:
                    yaml.dump(self.config_data, file, default_flow_style=False, sort_keys=False)
            elif self.config_file.endswith('.json'):
                with open(self.config_file, 'w') as file:
                    json.dump(self.config_data, file, indent=4)

            self.status_label.setText(f"Config saved to: {self.config_file}")
            self.mark_config_saved()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving config: {e}")

    def save_as_config(self):
        """Save configuration as new file"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration File",
            default_path,
            "YAML files (*.yml *.yaml);;JSON files (*.json);;All files (*.*)",
        )

        if filename:
            if not filename.endswith(('.yml', '.yaml', '.json')):
                filename += '.yml'
            self.config_file = filename
            self.save_config()

    def open_config(self):
        """Open configuration file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Configuration File",
            default_path,
            "Config files (*.yml *.yaml *.json);;YAML files (*.yml *.yaml);;JSON files (*.json);;All files (*.*)",
        )

        if filename:
            try:
                new_config = self.load_config(filename)
                if new_config:
                    self.config_data = new_config
                    self.config_file = filename
                    self.manual_edits.clear()
                    self.detect_manual_edits()
                    self.status_label.setText(f"Config loaded from: {filename}")
                    self.update_all_widgets()
                    self.mark_config_saved()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error opening config: {e}")

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
                if isinstance(value, list):
                    self._set_widget_value(widget, ', '.join(str(v) for v in value))
                else:
                    self._set_widget_value(widget, value)

    def execute_pipeline(self):
        """Execute the pipeline"""
        self.terminal_output.setPlainText("Executing pipeline...\n")

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting...")

        # Reset every stage icon to waiting at the start of each run.
        self._last_running_stage = None
        for key, _ in PIPELINE_STAGES:
            self.set_stage_status(key, 'waiting')

        self.execute_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)

        # Use 'python -m seshat.cli run' so we always use the same
        # interpreter as the GUI, regardless of whether 'seshat' is on PATH.
        args = ['-m', 'seshat.cli', 'run']
        if self.config_file:
            args += ['--config', self.config_file]

        self._stdout_buffer = ''

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(args)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        env = QProcessEnvironment.systemEnvironment()
        env.insert('FORCE_COLOR', '1')
        env.insert('PYTHONUNBUFFERED', '1')
        env.insert('SESHAT_PROGRESS_JSON', '1')
        process.setProcessEnvironment(env)

        process.readyReadStandardOutput.connect(self._handle_process_output)
        process.finished.connect(self._handle_process_finished)
        process.errorOccurred.connect(self._handle_process_error)

        self.terminal_process = process
        process.start()

    def _handle_process_output(self):
        """Read available subprocess output, split into complete lines, and
        dispatch each to the progress-event parser or the terminal pane.
        Runs directly on the GUI thread (QProcess signals), so no manual
        thread + after(0, ...) marshaling is needed here, unlike the old
        subprocess.Popen + threading.Thread implementation."""
        if self.terminal_process is None:
            return
        data = bytes(self.terminal_process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self._stdout_buffer += data
        while '\n' in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split('\n', 1)
            line += '\n'
            if self.maybe_handle_progress_event(line):
                continue
            cleaned_line = self.clean_terminal_output(line)
            self.append_output(cleaned_line)

    def _handle_process_finished(self, exit_code, exit_status):
        """Handle subprocess completion (mirrors the old run_pipeline()
        thread's post-loop wait()+returncode handling)."""
        if self._stdout_buffer:
            if not self.maybe_handle_progress_event(self._stdout_buffer):
                self.append_output(self.clean_terminal_output(self._stdout_buffer))
            self._stdout_buffer = ''

        self.terminal_process = None

        if exit_code != 0:
            # Best-effort fallback: the process ended without a clean
            # 'error' event for whichever stage was mid-flight (e.g. killed,
            # or crashed before it could emit one).
            self._mark_stuck_stage_error()

        self.append_output(f"\nProcess finished with exit code: {exit_code}\n")
        self.reset_buttons()

    def _handle_process_error(self, error):
        """Handle QProcess errors. Only QProcess.ProcessError.FailedToStart
        is handled here: that is the one error case where 'finished' is
        never subsequently emitted. Every other error (e.g. Crashed) is
        followed by a 'finished' signal, which already performs the same
        cleanup via _handle_process_finished - handling it twice here too
        would double-append output and double-reset buttons."""
        if error != QProcess.ProcessError.FailedToStart:
            return
        self._mark_stuck_stage_error()
        self.append_output("Error running pipeline: process failed to start\n")
        self.terminal_process = None
        self.reset_buttons()

    def abort_pipeline(self):
        """Abort the running pipeline"""
        if self.terminal_process:
            try:
                self.terminal_process.terminate()
                self.append_output("\n*** Pipeline execution aborted by user ***\n")
                self._mark_stuck_stage_error()

                QTimer.singleShot(1000, self._force_kill_if_still_running)

            except Exception as e:
                self.append_output(f"Error aborting process: {e}\n")
            finally:
                self.reset_buttons()

    def _force_kill_if_still_running(self):
        """Follow-up to terminate(): force-kill the subprocess if it hasn't
        exited after the grace period."""
        if self.terminal_process is not None and \
                self.terminal_process.state() != QProcess.ProcessState.NotRunning:
            self.terminal_process.kill()
            self.append_output("*** Process forcefully terminated ***\n")

    def clean_terminal_output(self, text):
        """Clean problematic Unicode characters from terminal output.

        Only the characters we have actually confirmed render on the
        affected Linux/Tk (and terminal) font stacks are preserved; anything
        else outside printable ASCII becomes '?' so an unsupported glyph
        degrades to a visible placeholder rather than a silent blank box.
        Kept unchanged for the PySide6 GUI pending re-verification of
        whether Qt's own font handling still needs this filtering (see
        STAGE_STATUS_ICONS comment above) - do not relax without testing on
        the real Rocky Linux target.
        """
        # Box drawing (frame) + block elements (progress bar) + the two
        # confirmed Geometric Shapes status glyphs. All verified to render
        # on the affected Linux Tk setup.
        safe_chars = (
            '─│┌┐└┘├┤┬┴┼'   # box drawing, print_summary_report's frame
            '█▉▊▋▌▍▎▏░▒▓▐'  # block elements, tqdm's progress bar
            '●○'                    # confirmed status glyphs
        )
        ansi_pattern = re.compile(r'(\033\[[0-9;]*m)')
        ansi_codes = ansi_pattern.findall(text)
        text_with_placeholders = ansi_pattern.sub('\x00ANSI\x00', text)
        # Keep printable ASCII, the line/tab control characters, the ANSI
        # placeholder, and the verified-safe glyph set above.
        text_cleaned = re.sub(
            r'[^\x20-\x7E\n\t\r\x00' + re.escape(safe_chars) + ']',
            '?',
            text_with_placeholders,
        )
        for code in ansi_codes:
            text_cleaned = text_cleaned.replace('\x00ANSI\x00', code, 1)

        return text_cleaned

    def reset_buttons(self):
        """Reset button states after pipeline execution"""
        self.execute_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)

    def set_stage_status(self, stage: str, status: str) -> None:
        """Update the circle status icon for one pipeline stage row."""
        label = self.stage_status_labels.get(stage)
        if label is None:
            return

        # Any status change cancels a previous blink cycle; 'running' below
        # starts a fresh one. This keeps at most one REC light blinking at a
        # time and guarantees a stopped/superseded stage doesn't keep ticking.
        self._stop_blink()

        if status == 'running':
            self._last_running_stage = stage
            # Reset the numeric bar for the new stage so a stale percentage
            # left over from the previous stage (or a stray sync-fallback
            # match) can't be mistaken for this stage's progress.
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            stage_name = dict(PIPELINE_STAGES).get(stage, stage or '')
            self.progress_label.setText(f"{stage_name}: starting...")

            icon, color = STAGE_STATUS_ICONS.get(status, ('', 'black'))
            self._blink_stage = stage
            self._blink_label = label
            self._blink_icon = icon
            self._blink_color = color
            self._blink_on = True
            label.setText(icon)
            label.setStyleSheet(f"color: {color};")
            self._blink_timer.start()
            return

        if self._last_running_stage == stage:
            # Stage reached a terminal state (done/error) or was reset to
            # waiting; it's no longer the "stuck" running stage.
            self._last_running_stage = None
        icon, color = STAGE_STATUS_ICONS.get(status, ('', 'black'))
        label.setText(icon)
        label.setStyleSheet(f"color: {color};")

    def _stop_blink(self):
        """Cancel any pending REC-light blink tick. Safe to call when no
        blink is active."""
        if self._blink_timer.isActive():
            self._blink_timer.stop()
        self._blink_stage = None
        self._blink_label = None

    def _blink_tick(self):
        """Toggle a 'running' stage's icon between visible and blank every
        _BLINK_INTERVAL_MS, mimicking a camcorder REC light. No-ops if the
        blink target was cleared (superseded by a new status) since the
        last tick was scheduled."""
        if self._blink_stage is None or self._blink_label is None:
            return
        self._blink_on = not self._blink_on
        self._blink_label.setText(self._blink_icon if self._blink_on else '')
        self._blink_label.setStyleSheet(f"color: {self._blink_color};")

    def _mark_stuck_stage_error(self):
        """Best-effort fallback: if a stage never received an explicit
        'done'/'error' event (process aborted, killed, crashed, or exited
        non-zero mid-stage), make sure its icon doesn't stay stuck on
        'running' forever."""
        if self._last_running_stage:
            self.set_stage_status(self._last_running_stage, 'error')

    def maybe_handle_progress_event(self, line: str) -> bool:
        """Parse one line of subprocess stdout for the structured progress
        protocol. Returns True if the line was a protocol event (and should
        not be shown in the terminal pane or fed to the legacy regex-based
        progress parser)."""
        if not line.startswith(_PROGRESS_SENTINEL):
            return False
        try:
            payload = json.loads(line[len(_PROGRESS_SENTINEL):].strip())
        except (ValueError, json.JSONDecodeError):
            return False
        if payload.get('event') == 'stage':
            self.set_stage_status(payload['stage'], payload['status'])
        elif payload.get('event') == 'task':
            self.set_task_progress(payload.get('stage'), payload.get('current'),
                                    payload.get('total'), payload.get('label'))
        return True

    def set_task_progress(self, stage, current, total, label=None):
        """Update the numeric progress bar/label from a structured 'task'
        event (e.g. 'file 42 of 137' within the currently running stage),
        replacing the previous regex-scraped byte/count fraction."""
        if not total or current is None:
            return
        percentage = max(0.0, min(100.0, (current / total) * 100))
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(percentage))
        stage_name = dict(PIPELINE_STAGES).get(stage, stage or '')
        text = f"{stage_name}: {current}/{total} ({percentage:.0f}%)"
        if label:
            text += f" \u2014 {label}"
        self.progress_label.setText(text)

    def append_output(self, text):
        """Append text to terminal output with ANSI color support"""
        apply_ansi_colors_to_qt(self.terminal_output, text)
        self.terminal_output.ensureCursorVisible()
        self.update_progress_from_text(text)

    def update_progress_from_text(self, text):
        """Extract progress information from terminal output and update progress bar.

        Note: the previous bare 'N/M' regex fallback (matching any two
        integers separated by a slash, anywhere in any log line) was
        removed. It could not distinguish a byte count (copy_raw) from a
        file count (copy_raw) from a subject count (opm_preprocess),
        applied the same '/1024^2 -> MB' conversion to all of them
        (nonsensical for small integer counts), and would false-positive on
        any ordinary log message that happened to contain two numbers and a
        slash. copy_raw and opm_preprocess now emit accurate, stage-
        attributed 'task' protocol events instead (see
        maybe_handle_progress_event/set_task_progress); this text-scraping
        fallback remains only for stages not yet instrumented (e.g. sync's
        rsync-style '--progress' percentage output).

        These fallbacks only fire while 'sync' is the running stage
        (tracked via self._last_running_stage, set by set_stage_status).
        copy_raw and opm_preprocess have real structured 'task' events now,
        so their own tqdm/mne text noise must never be allowed to touch the
        bar here - a stray 'NN%'-looking or 'N it [...]' substring in an
        unrelated log line would otherwise silently overwrite an accurate
        percentage with a bogus one.
        """
        if self._last_running_stage != 'sync':
            return

        match = re.search(r'(\d+)%', text)
        if match:
            percentage = int(match.group(1))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percentage)
            self.progress_label.setText(f"Progress: {percentage}%")
            return

        match = re.search(r'(\d+)it \[[\d:]+<[\d:]+', text)
        if match:
            if self.progress_bar.minimum() == 0 and self.progress_bar.maximum() == 100:
                # Switch to Qt's indeterminate/"busy" mode (0,0 range),
                # equivalent to ttk.Progressbar(mode='indeterminate').
                self.progress_bar.setRange(0, 0)
            return

        # Note: the previous blanket 'finished'/'completed'/'done' substring
        # match was removed. It fired on ANY line containing those words -
        # including per-item log lines emitted well before the run (or even
        # the current stage) actually finished, e.g. opm_preprocess.py's
        # per-session "HPI fit complete" and per-subject "Completed N/M
        # subjects" messages, and copy.py's end-of-stage (not end-of-run)
        # "Copy completed" message - each of which would immediately and
        # permanently snap the bar to 100%. True stage completion is now
        # signalled exclusively via the structured 'done' stage event (see
        # set_stage_status), which drives the per-stage status icon instead
        # of this numeric bar.

    def show(self):
        """Show the window and run the Qt event loop until it is closed."""
        super().show()
        app = QApplication.instance()
        if app is not None:
            app.exec()

    def quit(self):
        """Quit the application"""
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()


def args_parser():
    parser = argparse.ArgumentParser(
        description='Configuration script for SESHAT pipeline (PySide6 version).',
        add_help=True,
    )
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    return parser.parse_args()


def config_UI(config_file: str = None):
    """Launch the configuration GUI and return the configuration"""
    app = QApplication.instance() or QApplication(sys.argv)
    window = ConfigMainWindow(config_file=config_file)
    window.show()
    return window.config_data


def main(config_file: str = None):
    """Main entry point"""
    args = args_parser()
    config_file = args.config or config_file
    app = QApplication.instance() or QApplication(sys.argv)
    window = ConfigMainWindow(config_file=config_file)
    window.show()


if __name__ == "__main__":
    main()
