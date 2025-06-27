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

default_output_path = 'neuro/data/local'
noise_patterns = ['empty', 'noise', 'Empty']
proc_patterns = ['tsss', 'sss', r'corr\d+', r'ds\d+', 'mc', 'avgHead']
headpos_patterns = ['trans', 'headpos']
opm_exceptions_patterns = ['HPIbefore', 'HPIafter', 'HPImiddle',
                           'HPIpre', 'HPIpost']

def log(
    message: str,
    level: str='info',
    logfile: str='log.log',
    logpath: str='.'):
    """
    Print colored messages to console and append to structured log file.
    
    Provides standardized logging with:
    - Color-coded console output (blue=info, yellow=warning, red=error)
    - Timestamped log file entries in tab-separated format
    - Automatic log directory and file creation
    - Console and file output synchronization
    
    Args:
        message (str): Message content to log
        level (str): Log severity ('info', 'warning', 'error')
        logfile (str): Log filename (default: 'log.log')
        logpath (str): Directory path for log file (default: current dir)
    
    Returns:
        None
        
    Side Effects:
        - Creates log directory if it doesn't exist
        - Creates log file with header if first use
        - Appends timestamped entry to log file
        - Prints color-coded message to console
        
    Log File Format:
        Level    Timestamp           Message
        -----    ---------           -------
        [INFO]   2025-01-27 14:30:15 Processing started
    
    Note:
        Uses ANSI color codes for terminal output formatting
    """

    # Define colors for different log levels
    level_colors = {
        'info': '\033[94m',   # Blue
        'warning': '\033[93m',   # Yellow
        'error': '\033[91m'    # Red
    }
    
    # Check if the log level is valid
    if level not in level_colors:
        print(f"Invalid log level '{level}'. Supported levels are: info, warning, error.")
        return

    # Get the current timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Format the message
    formatted_message = f"""
    {level_colors[level]}[{level.upper()}] {timestamp}
    {message}\033[0m
     """

    if not exists(logpath):
        os.makedirs(logpath, exist_ok=True)
    # Create the log file if it doesn't exist
    if not exists(f'{logpath}/{logfile}'):
        with open(f'{logpath}/{logfile}', 'w') as f:
            f.write('Level\tTimestamp\tMessage\n')
            f.write('-----\t---------\t-------\n')
    
    # Write the message to the log file
    with open(f'{logpath}/{logfile}', 'a') as f:
        f.write(f"[{level.upper()}]\t{timestamp}\t{message}\n")
    print(formatted_message)


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
    participant = re.search(r'(NatMEG_|sub-)(\d+)', file_name).group(2)
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
        task = re.split('_', basename(file_name), flags=re.IGNORECASE)[-2].replace('file-', '')
        task = re.split('opm', task, flags=re.IGNORECASE)[0]

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
