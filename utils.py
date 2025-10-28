"""
Utility Functions for NatMEG Processing Pipeline

Common helper functions used across the MEG processing workflow including
logging, file handling, configuration management, and filename parsing.

Author: Andreas Gerhardsson
"""

from datetime import datetime
import sys
import re
from os.path import basename, join, isdir, exists
import os
from glob import glob
import logging
from logging import handlers
from typing import Optional, Dict, Tuple
from pathlib import Path
import json
import yaml

# tkinter file dialog imports
from tkinter import filedialog


# Predefined patterns for filename parsing

default_output_path = '/neuro/data/local'
noise_patterns = ['empty', 'noise', 'Empty']
proc_patterns = ['tsss', 'sss', r'corr\d+', r'ds\d+', 'mc', 'avgHead']
headpos_patterns = ['headpos', 'headshape']
opm_exceptions_patterns = ['HPIbefore', 'HPIafter', 'HPImiddle',
                           'HPIpre', 'HPIpost']

###############################################################################
# Directory management and configuration handling
###############################################################################

def askdirectory(**kwargs):
    """tkinter filedialog.askdirectory wrapper"""
    
    directory = filedialog.askdirectory(
        title=kwargs.get('title', 'Select Directory'),
        initialdir=kwargs.get('initialdir', '')
    )

    return directory

def project_paths(config: str, init=False):
    """Create a directory structure for a new project."""
    
    if isinstance(config, str):
        if config.endswith('.json'):
            with open(config, 'r') as f:
                config = json.load(f)
        elif config.endswith('.yml') or config.endswith('.yaml'):
            with open(config, 'r') as f:
                config = yaml.safe_load(f)
        else:
            raise ValueError("Unsupported configuration file format. Use .json or .yml/.yaml")
    
    base_root = config['Project'].get('Root', '.')
    project_name = config['Project']['Name']
    project_root = Path(os.path.join(base_root, project_name))
    raw_root = config['Project'].get('Raw', project_root / 'raw')
    bids_root = config['Project'].get('BIDS', project_root / 'bids')
    log_file = config['Project'].get('LogFile', 'pipeline_log.log')
    
    paths = {
        'project_root': project_root,
        'raw': Path(raw_root),
        'scripts': project_root / 'scripts',
        'logs': project_root / 'logs',
        'docs': project_root / 'docs'
    }
    
    if init:
        # Create project directories
        try:
            for path in paths.values():
                if not path.exists():
                    path.mkdir(parents=True)
                    print(f"The directory '{path}' was created.")
                else:
                    print(f"The directory '{path}' already exists.")
        except Exception as e:
            print(f"An error occurred: {e}")
    
    paths['log_file'] = paths['logs'] / log_file
    paths['bids'] = bids_root
    paths['sinuhe'] = config['Project'].get('Sinuhe raw', None)
    paths['kaptah'] = config['Project'].get('Kaptah raw', None)
    paths['Calibration'] = config['Project'].get('Calibration', None)
    paths['Crosstalk'] = config['Project'].get('Crosstalk', None)
    
    return paths

def askForConfig():
    """
    Open GUI file dialog for configuration file selection.
    
    Presents user with file browser dialog filtered for YAML and JSON
    configuration files. Provides fallback when no config file is specified
    via command line or programmatic interface.
    
    Supported Formats:
    - YAML files: .yml, .yaml extensions
    - JSON files: .json extension
    
    Args:
        None
    
    Returns:
        str: Full path to selected configuration file
        
    Side Effects:
        - Opens tkinter file dialog window
        - Prints selected file path to console
        - Exits program with code 1 if no file selected
        
    Raises:
        SystemExit: If user cancels dialog without selecting file
        
    Initial Directory:
        Defaults to '/neuro/data/local' for convenient navigation
    """
    # Create hidden root window
    # if not exists(default_output_path):
    #     default_output_path = '.'
    
    config_file = filedialog.askopenfilename(
        title="Select Configuration File",
        initialdir=default_output_path,
        filetypes=[
            ("YAML files", "*.yml *.yaml"),
            ("JSON files", "*.json"),
            ("All files", "*.*")
        ]
    )

    if not config_file:
        print('No configuration file selected. Exiting opening dialog')
        sys.exit(1)
    
    print(f'{config_file} selected')
    return config_file

###############################################################################
# Centralized logging setup (colored console + structured file log)
###############################################################################

_LOGGER_NAME = 'NatMEG'
_CONFIGURED: bool = False
_FILE_HANDLER_REGISTRY: Dict[str, logging.Handler] = {}
_CONSOLE_HANDLER: Optional[logging.Handler] = None
class _ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: '\033[90m',
        logging.INFO: '\033[94m',
        logging.WARNING: '\033[93m',
        logging.ERROR: '\033[91m',
        logging.CRITICAL: '\033[95m',
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, '')
        msg = super().format(record)
        # Keep color codes for Tk terminal to render
        return f"{color}{msg}{self.RESET}"


def configure_logging(log_dir: str = '.',
                      log_file: str = 'pipeline.log',
                      console_level: int = logging.INFO,
                      file_level: int = logging.DEBUG,
                      rotate: bool = False,
                      max_bytes: int = 5_000_000,
                      backup_count: int = 3) -> logging.Logger:
    """Configure centralized logging for the project.

    - Adds a colored console handler (ANSI) for interactive use.
    - Adds a structured TSV file handler including filename:line.
    - Safe to call multiple times; reuses existing handlers.
    """
    global _CONFIGURED, _CONSOLE_HANDLER

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Console handler (singleton)
    if _CONSOLE_HANDLER is None:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(console_level)
        ch.setFormatter(_ColoredFormatter('[%(levelname)s] %(asctime)s %(name)s:%(lineno)d - %(message)s'))
        logger.addHandler(ch)
        _CONSOLE_HANDLER = ch

    # File handler per file path
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    file_path = os.path.join(log_dir, log_file)

    # Write header on first creation
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            f.write('timestamp\tlevel\tlogger\tlocation\tmessage\n')

    if file_path not in _FILE_HANDLER_REGISTRY:
        if rotate:
            fh = handlers.RotatingFileHandler(file_path, maxBytes=max_bytes, backupCount=backup_count)
        else:
            fh = logging.FileHandler(file_path)
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)s\t%(name)s\t%(filename)s:%(lineno)d\t%(message)s'))
        logger.addHandler(fh)
        _FILE_HANDLER_REGISTRY[file_path] = fh

    _CONFIGURED = True
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    base = logging.getLogger(_LOGGER_NAME)
    return base.getChild(name) if name else base


def _normalize_legacy_call(process: str, message: str, level: str) -> Tuple[str, str, str]:
    """Support both legacy and misordered calls.
    If called as log(message, 'error', ...), swap to (process, message, level).
    """
    levels = {'info', 'warning', 'error', 'debug', 'critical'}
    if message in levels and level == 'info':
        # Likely called as log(message, 'error', ...)
        return ('App', process, message)
    return (process, message, level)


def log(
    process: str,
    message: str,
    level: str = 'info',
    log_file_path: str = './log.log',
    logfile: Optional[str] = None,
    logpath: Optional[str] = None
):
    """Project-wide logging wrapper (backward-compatible).

    - Uses centralized logging with colored console + TSV file output.
    - Accepts legacy utils.log signature and common misordered usage.
    - Ensures a file handler for the given log_file_path exists.
    
    Args:
        process: Process name for logging context
        message: Log message content
        level: Log level ('debug', 'info', 'warning', 'error', 'critical')
        log_file_path: Full path to log file (preferred method)
        logfile: Legacy parameter - filename only (deprecated, use log_file_path)
        logpath: Legacy parameter - directory only (deprecated, use log_file_path)
    """
    process, message, level = _normalize_legacy_call(process, message, level)
    level = level.lower()

    # Handle backward compatibility
    if logfile is not None and logpath is not None:
        # Legacy call with separate logfile and logpath
        file_path = os.path.join(logpath, logfile)
        log_dir = logpath
        log_file = logfile
    else:
        # New unified log_file_path
        file_path = log_file_path
        log_dir = os.path.dirname(file_path)
        log_file = os.path.basename(file_path)

    if not _CONFIGURED:
        # Default configuration if not yet configured
        configure_logging(log_dir=log_dir, log_file=log_file)
    else:
        # Ensure file handler exists for this target
        if file_path not in _FILE_HANDLER_REGISTRY:
            configure_logging(log_dir=log_dir, log_file=log_file)

    import inspect
    
    # Get the caller's frame to show the actual script that called log()
    frame = inspect.currentframe()
    caller_filename = 'unknown'
    caller_lineno = 0
    caller_funcname = 'unknown'
    
    try:
        # Go up the stack to find the caller (skip this function and any wrapper functions)
        if frame and frame.f_back:
            caller_frame = frame.f_back
            while caller_frame and caller_frame.f_code.co_filename.endswith('utils.py'):
                caller_frame = caller_frame.f_back
            
            if caller_frame:
                caller_filename = os.path.basename(caller_frame.f_code.co_filename)
                caller_lineno = caller_frame.f_lineno
                caller_funcname = caller_frame.f_code.co_name
    finally:
        del frame  # Prevent reference cycles
    
    logger = get_logger(process)
    log_fn = getattr(logger, level if level in ('debug', 'info', 'warning', 'error', 'critical') else 'info')
    
    # Create a custom log record with the caller's information
    if hasattr(logger, '_log'):
        # Use the internal _log method to set custom location info
        log_level = getattr(logging, level.upper(), logging.INFO)
        # Create a LogRecord manually with correct pathname and lineno
        record = logger.makeRecord(
            logger.name, log_level, caller_filename, caller_lineno,
            message, (), None, caller_funcname
        )
        logger.handle(record)
    else:
        # Fallback to regular logging
        log_fn(message)


###############################################################################
# File pattern matching and filename parsing
###############################################################################

def file_contains(file: str, pattern: list):
    """
    Check if filename contains any of the specified patterns using regex.
    
    Performs case-sensitive pattern matching against filename using compiled
    regular expressions for efficient multi-pattern searching.
    
    Args:
        file (str): Filename or path to check
        pattern (list): List of regex patterns to match against
    
    Returns:
        bool: True if any pattern matches, False otherwise
        
    Examples:
        >>> file_contains('test_tsss_mc.fif', proc_patterns)
        True
        >>> file_contains('empty_room.fif', noise_patterns)
        True
        >>> file_contains('regular_data.fif', headpos_patterns)
        False
    
    Note:
        Patterns are joined with '|' (OR) operator for single regex compilation
    """
    return bool(re.compile('|'.join(pattern)).search(file))

def extract_info_from_filename(file_name: str):
    """
    Parse MEG filenames to extract standardized metadata components.
    
    Comprehensive filename parser that handles both TRIUX (NatMEG_) and 
    BIDS (sub-) naming conventions. Extracts participant IDs, task names,
    processing stages, data types, and file structure information using
    regex pattern matching.
    
    Supported Filename Formats:
    - TRIUX: NatMEG_001_TaskName_proc-options_meg.fif
    - BIDS: sub-001_ses-01_task-TaskName_proc-options_meg.fif
    - OPM: Various Kaptah-specific patterns
    
    Parsing Features:
    - Participant ID extraction (zero-padded numbers)
    - Task name identification with intelligent filtering
    - Processing stage detection (tSSS, SSS, movement correction, etc.)
    - Data type classification (MEG, EEG, OPM, behavioral)
    - Split file detection (-1.fif, -2.fif, etc.)
    - Head position file identification (trans, headpos)
    - Noise recording classification (empty room variants)
    
    Args:
        file_name (str): Full path or filename to parse
    
    Returns:
        dict: Parsed filename components with keys:
            - filename (str): Original input filename
            - participant (str): Participant ID (e.g., '001')
            - task (str): Task name (e.g., 'Phalanges', 'AudOdd')
            - split (str): Split file suffix (e.g., '-1', '-2') or empty
            - processing (list): Processing steps applied (e.g., ['tsss', 'mc'])
            - description (list): File type descriptors (e.g., ['trans', 'headpos'])
            - datatypes (list): Data modalities (e.g., ['meg', 'opm'])
            - suffix (str): Special suffix (e.g., 'headshape') or None
            - extension (str): File extension (e.g., '.fif')
    
    Special Handling:
    - OPM files: Uses position-based task extraction
    - Noise files: Standardizes to 'Noise', 'NoiseBefore', 'NoiseAfter'
    - Multi-word tasks: Converts to CamelCase (e.g., 'aud_odd' → 'AudOdd')
    - Split files: Preserves original numbering scheme
    
    Examples:
        >>> extract_info_from_filename('NatMEG_001_Phalanges_tsss_mc_meg.fif')
        {
            'filename': 'NatMEG_001_Phalanges_tsss_mc_meg.fif',
            'participant': '001',
            'task': 'Phalanges',
            'split': '',
            'processing': ['tsss', 'mc'],
            'description': [],
            'datatypes': ['meg'],
            'extension': '.fif'
        }
        
        >>> extract_info_from_filename('sub-001_task-empty_room_after.fif')
        {
            'filename': 'sub-001_task-empty_room_after.fif',
            'participant': '001', 
            'task': 'NoiseAfter',
            'split': '',
            'processing': [],
            'description': [],
            'datatypes': ['meg'],
            'extension': '.fif'
        }
    
    Note:
        Function handles edge cases and various naming inconsistencies
        commonly found in MEG datasets across different acquisition systems
    """
    suffix = ''
    desc = ''
    proc = ['']
    split = ''
    datatypes = ['']
    extension = ''
    
    # Extract participant, task, processing, datatypes and extension
    participant = re.search(r'(NatMEG_|sub-)(\d+)', file_name).group(2).zfill(4)
    extension = '.' + re.search(r'\.(.*)', basename(file_name)).group(1)
    datatypes = list(set([r.lower() for r in re.findall(r'(meg|raw|opm|eeg|behav)', basename(file_name), re.IGNORECASE)] +
                         ['opm' if 'kaptah' in file_name else '']))
    suffix = 'meg' if any(item in datatypes for item in ['raw', 'meg']) else ''
    datatypes = [d for d in datatypes if d != '']
    
    proc = re.findall('|'.join(proc_patterns), basename(file_name))
    
    if file_contains(basename(file_name), ['trans']):
        desc = 'trans'
        suffix = 'meg'
    
    if file_contains(file_name, headpos_patterns):
        suffix = 'headshape'

    split = re.search(r'(\-\d+\.fif)', basename(file_name))
    split = split.group(1).strip('.fif') if split else ''
    
    exclude_from_task = '|'.join(['NatMEG_'] + ['sub-'] + ['proc']+ datatypes + [participant] + [extension]  + [suffix] + headpos_patterns + proc + [split] + ['\\+'] + ['\\-'] + [desc])
    
    if file_contains(file_name, opm_exceptions_patterns):
        datatypes.append('opm')
    
    if 'opm' in datatypes or 'kaptah' in file_name:    

        exclude_from_task = '|'.join(['NatMEG_'] + ['sub-'] + ['proc-']+ datatypes + [participant] + [extension] + proc + [split] + ['\\+'] + ['\\-'] + ['file']+ [desc] + [r'\d{8}_', r'\d{6}_'])
        if not file_contains(file_name, opm_exceptions_patterns):
            exclude_from_task += '|hpi|ds'

        task = re.sub(exclude_from_task, '', basename(file_name), flags=re.IGNORECASE)
        
        proc = re.findall('|'.join(proc_patterns + ['hpi', 'ds']), basename(file_name))

    else:
        task = re.sub(exclude_from_task, '', basename(file_name), flags=re.IGNORECASE)
    task = [t for t in task.split('_') if t]
    if len(task) > 1:
        task = ''.join([t.title() for t in task])
    else:
        task = task[0]

    if file_contains(task, noise_patterns):
        try:
            task = f'Noise{re.search("before|after", task.lower()).group().title()}'
        except:
            task = 'Noise'

    info_dict = {
        'filename': file_name,
        'participant': participant,
        'task': task,
        'split': split,
        'processing': proc,
        'description': desc,
        'datatypes': datatypes,
        'suffix': suffix,
        'extension': extension
    }
    
    return info_dict


 ###############################################################################
 # Other useful utilities
###############################################################################
def delete_files(root, pattern, test=True, recursive=True):
    files = sorted(glob(f'**/{pattern}', root_dir=root, recursive=recursive))
    if not test:
        print("##### DELETING #####")
        for file in files:
            print(f'{root}/{file}')
            os.remove(f'{root}/{file}')
        print("##### Files deleted #####")
    else:
        print("##### TESTING #####")
        for file in files:
            print(f'{root}/{file}')
        print("##### TEST: No files deleted #####")

def copy_files(src, dst, pattern, test=True, recursive=True):
    files = glob(f'**/{pattern}', root_dir=src, recursive=recursive)
    if not test:
        for file in files:
            print("##### COPYING #####")
            print(f'{src}/{file}', f'{dst}/{file}')
            copy2(f'{src}/{file}', dst)
            print("##### Files copied #####")
    else:
        for file in files:
            print("##### TESTING #####")
            print(f'{src}/{file}', f'{dst}/{file}')
            print("##### TEST: No files copied #####")