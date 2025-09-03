"""
Utility Functions for NatMEG Processing Pipeline

Common helper functions used across the MEG processing workflow including
logging, file handling, configuration management, and filename parsing.

Author: Andreas Gerhardsson
"""

from datetime import datetime
import sys
from tkinter.filedialog import askopenfilename, asksaveasfile
import re
from os.path import basename, join, isdir, exists
import os
from glob import glob
import pandas as pd
from os.path import exists, dirname
import os
import logging
from logging import handlers
from typing import Optional, Dict, Tuple

default_output_path = 'neuro/data/local'
noise_patterns = ['empty', 'noise', 'Empty']
proc_patterns = ['tsss', 'sss', r'corr\d+', r'ds\d+', 'mc', 'avgHead']
headpos_patterns = ['trans', 'headpos']
opm_exceptions_patterns = ['HPIbefore', 'HPIafter', 'HPImiddle',
                           'HPIpre', 'HPIpost']

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
    logfile: str = 'log.log',
    logpath: str = '.'
):
    """Project-wide logging wrapper (backward-compatible).

    - Uses centralized logging with colored console + TSV file output.
    - Accepts legacy utils.log signature and common misordered usage.
    - Ensures a file handler for the given logpath/logfile exists.
    """
    process, message, level = _normalize_legacy_call(process, message, level)
    level = level.lower()

    if not _CONFIGURED:
        # Default configuration if not yet configured
        configure_logging(log_dir=logpath, log_file=logfile)
    else:
        # Ensure file handler exists for this target
        file_path = os.path.join(logpath, logfile)
        if file_path not in _FILE_HANDLER_REGISTRY:
            configure_logging(log_dir=logpath, log_file=logfile)

    logger = get_logger(process)
    log_fn = getattr(logger, level if level in ('debug', 'info', 'warning', 'error', 'critical') else 'info')
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
    
    # Extract participant, task, processing, datatypes and extension
    participant = re.search(r'(NatMEG_|sub-)(\d+)', file_name).group(2).zfill(4)
    extension = '.' + re.search(r'\.(.*)', file_name).group(1)
    datatypes = list(set([r.lower() for r in re.findall(r'(meg|raw|opm|eeg|behav)', basename(file_name), re.IGNORECASE)] +
                         ['opm' if 'kaptah' in file_name else '']))
    datatypes = [d for d in datatypes if d != '']

    proc = re.findall('|'.join(proc_patterns), basename(file_name))
    desc = re.findall('|'.join(headpos_patterns), basename(file_name))

    split = re.search(r'(\-\d+\.fif)', basename(file_name))
    split = split.group(1).strip('.fif') if split else ''
    
    exclude_from_task = '|'.join(['NatMEG_'] + ['sub-'] + ['proc']+ datatypes + [participant] + [extension] + proc + [split] + ['\\+'] + ['\\-'] + desc)
    
    if file_contains(file_name, opm_exceptions_patterns):
        datatypes.append('opm')
    
    if 'opm' in datatypes or 'kaptah' in file_name:    

        exclude_from_task = '|'.join(['NatMEG_'] + ['sub-'] + ['proc-']+ datatypes + [participant] + [extension] + proc + [split] + ['\\+'] + ['\\-'] + ['file']+ desc + [r'\d{8}_', r'\d{6}_'])
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
        'extension': extension
    }
    
    return info_dict

###############################################################################
# Configuration Management
###############################################################################

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
        Defaults to 'neuro/data/local' for convenient navigation
    """
    config_file = askopenfilename(
        title='Select config file',
        filetypes=[('YAML files', ['*.yml', '*.yaml']), ('JSON files', '*.json')],
        initialdir=default_output_path)

    if not config_file:
        print('No configuration file selected. Exiting opening dialog')
        sys.exit(1)
    
    print(f'{config_file} selected')
    return config_file
