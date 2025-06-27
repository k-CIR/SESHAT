#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MaxFilter Signal Space Separation (SSS) Processing Pipeline

This module provides a comprehensive interface for applying Elekta MaxFilter
to MEG data, including temporal Signal Space Separation (tSSS), movement
compensation, and head position tracking.

Author: Andreas Gerhardsson
Created: Friday, 26 June 2025

Based on an original MaxFilter shell script by Mikkel Vinding and Lau Møller Andersen

"""
#%%
from glob import glob
import os
from os.path import exists, basename, dirname, isdir
import sys
import re
import tkinter as tk
from tkinter.filedialog import askdirectory, askopenfilename, asksaveasfile
import json
import yaml
import pandas as pd
import subprocess
import argparse
from datetime import datetime
from shutil import copy2
from copy import deepcopy
import mne
from mne.transforms import (invert_transform,
                            read_trans, write_trans)
from mne.preprocessing import compute_average_dev_head_t
from mne.chpi import (compute_chpi_amplitudes, compute_chpi_locs,
                      head_pos_to_trans_rot_t, compute_head_pos,
                      write_head_pos,
                      read_head_pos)
import matplotlib.patches as mpatches
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import (
    log,
    proc_patterns,
    noise_patterns,
    file_contains,
    askForConfig
)

###############################################################################
# Global variables
###############################################################################

exclude_patterns = [r'-\d+.fif', '_trans', 'opm',  'eeg', 'avg.fif']


###############################################################################
# Configuration and Parameter Functions
###############################################################################

def get_parameters(config):
    """
    Extract and validate MaxFilter configuration parameters.
    
    Processes configuration from file (JSON/YAML) or dictionary, extracting
    MaxFilter-specific settings and merging with project parameters for
    calibration files, data paths, and processing options.
    
    Args:
        config (str or dict): Path to config file or configuration dictionary
                             containing 'maxfilter' and 'project' sections
    
    Returns:
        dict: Merged MaxFilter configuration with keys:
            - standard_settings: Basic processing parameters
            - advanced_settings: Expert-level options
            - Includes calibration/crosstalk file paths from project config
    
    Raises:
        ValueError: If unsupported configuration file format provided
    """
    if isinstance(config, str):
        if config.endswith('.json'):
            with open(config, 'r') as f:
                config_dict = json.load(f)
        elif config.endswith('.yml') or config.endswith('.yaml'):
            with open(config, 'r') as f:
                config_dict = yaml.safe_load(f)
        else:
            raise ValueError("Unsupported configuration file format. Use .json or .yml/.yaml")
    elif isinstance(config, dict):
        config_dict = deepcopy(config)
    
    maxfilter_dict = deepcopy(config_dict['maxfilter'])
    maxfilter_dict['advanced_settings']['cal'] = config_dict['project']['Calibration']
    maxfilter_dict['advanced_settings']['ctc'] = config_dict['project']['Crosstalk']
    maxfilter_dict['standard_settings']['project_name'] = config_dict['project']['name']
    maxfilter_dict['standard_settings']['data_path'] = config_dict['project']['squidMEG']
    maxfilter_dict['standard_settings']['out_path'] = config_dict['project']['squidMEG']
    
    return maxfilter_dict

def match_task_files(files, task: str):
    """
    Filter file list to match specific task while excluding processed files.
    
    Identifies raw files for a given task by matching task name in filename
    and excluding already processed files, split files, and other derivatives.
    
    Args:
        files (list): List of FIF filenames to filter
        task (str): Task name to match (e.g., 'Phalanges', 'AudOdd')
    
    Returns:
        list: Filtered filenames containing task name, excluding processed files
        
    Note:
        Excludes files matching exclude_patterns and proc_patterns from utils
    """
    matched_files = [f for f in files if not file_contains(basename(f).lower(), exclude_patterns + proc_patterns) and task in f]
    return matched_files

def plot_movement(raw, head_pos, mean_trans):
    """
    Generate head movement visualization for quality assessment.
    
    Creates movement trace plots comparing original head position with
    average position transformation, useful for assessing subject movement
    and transformation quality.
    
    Args:
        raw (mne.io.Raw): Raw MEG data with device-head transformation
        head_pos (str or array): Head position file path or position array
        mean_trans (str or dict): Mean transformation file path or transform
    
    Returns:
        matplotlib.Figure: Movement trace plot with original and average positions
        
    Side Effects:
        - Displays translation traces in mm
        - Shows original position (red) vs average (green)
        - Includes legend and tight layout
    """

    if isinstance(head_pos, str):
        head_pos = read_head_pos(head_pos)
    if isinstance(mean_trans, str):
        mean_trans = read_trans(mean_trans)
        
    original_head_dev_t = invert_transform(raw.info["dev_head_t"])
    
    """
    Plot trances of movement for insepction. Uses mne.viz.plot_head_positions
    """
    fig = mne.viz.plot_head_positions(head_pos, mode='traces', show=False)
    red_patch = mpatches.Patch(color='r', label='Original')
    green_patch = mpatches.Patch(color='g', label='Average')

    for ax, ori, av in zip(fig.axes[::2],
                            original_head_dev_t['trans'][:3, 3],
                            mean_trans['trans'][:3, 3]):
        ax.axhline(1000*ori, color="r")
        ax.axhline(1000*av, color="g")
        
    fig.legend(handles=[red_patch, green_patch], loc='upper left')
    fig.tight_layout()
    return fig

###############################################################################
# Parameter Setting Classes
###############################################################################

class set_parameter:
    """
    Container for MaxFilter parameter strings in multiple formats.
    
    Stores parameter values for both Elekta MaxFilter command-line interface
    and MNE-Python equivalents, along with descriptive strings for file naming.
    
    Attributes:
        mxf (str): Elekta MaxFilter command-line parameter
        mne_mxf (str): MNE-Python equivalent parameter  
        string (str): Descriptive string for output file naming
    """
    def __init__(self, mxf, mne_mxf, string):
        self.mxf = mxf
        self.mne_mxf = mne_mxf
        self.string = string

class MaxFilter:
    """
    Comprehensive MaxFilter processing pipeline for MEG data.
    
    Handles complete Signal Space Separation workflow including:
    - Head position tracking and movement compensation
    - Temporal SSS for interference suppression
    - Bad channel detection and correction
    - Coordinate system transformations
    - Parallel processing of multiple subjects/sessions
    
    Key Features:
    - Automatic parameter validation and setting
    - Task-specific processing configurations
    - Empty room recording handling
    - Movement compensation with head position files
    - Quality control and logging
    - BIDS-compatible output naming
    """
    
    def __init__(self, config_dict: dict, **kwargs):
        """
        Initialize MaxFilter processor with configuration parameters.
        
        Processes configuration dictionary and converts string flags ('on'/'off')
        to boolean values for internal parameter handling.
        
        Args:
            config_dict (dict): Complete configuration including maxfilter settings
            **kwargs: Additional parameters (currently unused)
        
        Side Effects:
            - Merges standard and advanced settings into self.parameters
            - Converts 'on'/'off' strings to True/False booleans
        """

        config_dict = get_parameters(config_dict)
        
        parameters = config_dict['standard_settings'] | config_dict['advanced_settings']
        
        # Convert 'on'/'off' to True/False in parameters
        for key, value in parameters.items():
            if value == 'on':
                parameters[key] = True
            elif value == 'off':
                parameters[key] = False

        self.parameters = parameters
    
    def create_task_headpos(self, 
                            data_path: str,
                            out_path: str,
                            task: str,
                            files: list | str,
                            overwrite=False,
                            **kwargs):
        """
        Generate average head position and transformation for task runs.
        
        Computes HPI-based head position tracking across multiple runs of the
        same task, creating average head position file and coordinate transformation
        for movement compensation during MaxFilter processing.
        
        Processing Steps:
        1. Load raw data files for the task
        2. Optionally merge runs with consistent head position
        3. Compute HPI amplitudes and locations
        4. Calculate continuous head position estimates
        5. Generate average transformation matrix
        6. Create movement visualization plot
        
        Args:
            data_path (str): Input directory containing raw files
            out_path (str): Output directory for head position files
            task (str): Task name for file naming
            files (list or str): Raw file(s) for head position calculation
            overwrite (bool): Whether to regenerate existing files
            **kwargs: Additional parameters passed to computation functions
        
        Returns:
            None
            
        Side Effects:
            - Creates {task}_headpos.pos file with continuous head positions
            - Creates {task}_trans.fif file with average transformation
            - Saves {task}_movement.png plot for quality control
            - Logs processing steps and file creation
        
        Notes:
            - Requires HPI coils active during recording
            - Merges runs if merge_runs parameter enabled
            - Uses compute_chpi_* functions from MNE for localization
        """

        parameters = self.parameters

        merge_headpos = parameters.get('merge_runs')

        headpos_name = f"{out_path}/{task}_headpos.pos"
        trans_file = f"{out_path}/{task}_trans.fif"
        fig_name = f"{out_path}/{task}_movement.png"

        if not exists(headpos_name) or overwrite:
            
            if isinstance(files, str):
                files = [files]
            raws = [mne.io.read_raw_fif(
                    f'{data_path}/{file}',
                    allow_maxshield=True,
                    verbose='error')
                        for file in files]
            
            if merge_headpos and len(files) > 1:
                raws[0].info['dev_head_t'] = raws[1].info['dev_head_t']
                raw = mne.concatenate_raws(raws)
            else:
                raw = raws[0]
            print(f"Creating average head position for files: {' | '.join(files)}")
            chpi_amplitudes = compute_chpi_amplitudes(raw)
            chpi_locs = compute_chpi_locs(raw.info, chpi_amplitudes)
            head_pos = compute_head_pos(raw.info, chpi_locs, verbose='error')
            
            write_head_pos(headpos_name, head_pos)
            print(f"Wrote headposition file to: {basename(headpos_name)}")
        else:
            print(f'{basename(headpos_name)} already exists. Skipping...')
        
        if not exists(trans_file) or overwrite:

            if isinstance(files, str):
                files = [files]
            raws = [mne.io.read_raw_fif(
                    f'{data_path}/{file}',
                    allow_maxshield=True,
                    verbose='error')
                        for file in files]
            
            if merge_headpos and len(files) > 1:
                raws[0].info['dev_head_t'] = raws[1].info['dev_head_t']
                raw = mne.concatenate_raws(raws)
            else:
                raw = raws[0]

            head_pos = read_head_pos(headpos_name)
            # trans, rot, t = head_pos_to_trans_rot_t(head_pos) 

            mean_trans = invert_transform(
                compute_average_dev_head_t(raw, head_pos))
            
            write_trans(trans_file, mean_trans, overwrite=True)
            print(f'Wrote trans file to {basename(trans_file)}')
        
        else:
            print(f'{basename(trans_file)} already exists. Skipping...')
        
        if not exists(fig_name) or overwrite:
            plot_movement(raw, headpos_name, trans_file).savefig(fig_name)

    def set_params(self, subject, session, task):
        """
        Configure MaxFilter parameters for specific subject/session/task.
        
        Dynamically sets all MaxFilter command-line parameters based on
        configuration settings, task type, and file availability. Handles
        special cases like empty room recordings and task-specific options.
        
        Parameter Categories:
        - Transformation: Head position correction and coordinate transforms
        - SSS/tSSS: Signal space separation and temporal extension
        - Movement compensation: HPI-based head tracking
        - Bad channel handling: Automatic and manual bad channel specification
        - Filtering: Line frequency and correlation thresholds
        - Calibration: Cal/ctc files and system-specific corrections
        
        Args:
            subject (str): Subject identifier (e.g., 'sub-001')
            session (str): Session identifier (e.g., '20250127')
            task (str): Task name affecting parameter selection
        
        Returns:
            None
            
        Side Effects:
            - Sets instance attributes for all MaxFilter parameters
            - Configures command strings for both Elekta and MNE interfaces
            - Adapts parameters based on task type (e.g., disables movement
              compensation for empty room recordings)
            - Generates BIDS-compatible processing suffix string
        
        Parameter Attributes Set:
            _trans, _force, _cal, _ctc, _ds, _tsss, _corr, _mc, 
            _autobad, _bad_channels, _linefreq, _proc, _merge_runs, _additional_cmd
        """
        parameters = self.parameters
            
        data_root = parameters.get('data_path')
        output_path = parameters.get('out_path')
        # Check if output path is set
        if not output_path:
            output_path = data_root

        subj_path = f'{output_path}/{subject}/{session}/triux'
        trans_file = f'{subj_path}/{task}_trans.fif'
        trans_conditions = parameters.get('trans_conditions')
        trans_option = parameters.get('trans_option')

        def set_trans(param=None):
            if 'continous' in trans_option and task in trans_conditions:
                if param:
                    mxf = '-trans %s' % param
                    mne_mxf = '--trans=%s' % param
                    string = 'avgHead'
            else:
                mxf=''
                mne_mxf = ''
                string = ''
                print('No information about trans')
                #sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _trans = set_trans(trans_file)
        
        # create set_force function
        def set_force(param=None):
            if param:
                mxf = '-force'
            elif not param:
                mxf = ''
            else:
                print('faulty "force" setting')
                sys.exit(1)
            return(mxf)
        _force = set_force(parameters.get('force'))
        
        def set_cal(param=None):
            if param:
                mxf = '-cal %s' % param
                mne_mxf = '--calibration=%s' % param
                string = 'cal_'
            else:
                print('no "cal" file found')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _cal = set_cal(parameters.get('cal'))
        
        def set_ctc(param=None):
            if param:
                mxf = '-ctc %s' % param
                mne_mxf = '--cross_talk=%s' % param
                string = 'ctc_'
            else:
                print('no "ctc" file found')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _ctc = set_ctc(parameters.get('ctc'))
        
        # create set_mc function (sets movecomp according to wishes above and abort if set incorrectly, this is a function such that it can be changed throughout the script if empty_room files are found) 
        def set_mc(param=None):
            if param:
                mxf = '-movecomp'
                mne_mxf = '--movecomp'
                string='mc'
            elif not param:
                mxf = ''
                mne_mxf = ''
                string = ''
            else:
                print('faulty "movecomp" setting')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _mc = set_mc(parameters.get('movecomp_default'))
        # If empty room file set tsss off and remove trans and headpos
        if file_contains(task, noise_patterns):
            _mc.mxf = ''
            _mc.mne_mxf = ''
            _mc.string = ''

        # create set_tsss function
        def set_tsss(param=None):
            if param:
                mxf = '-st'
                mne_mxf='--st'
                string='tsss'
            elif not param:
                mxf = ''
                mne_mxf=''
                string=''
            else:
                print('faulty "tsss" setting')
                sys.exit(1)
            return(set_parameter(mxf,mne_mxf, string))
        _tsss = set_tsss(parameters.get('tsss_default'))
        
        # create set_ds function
        def set_ds(param=None):
            if param:
                if int(parameters.get('downsample_factor')) > 1:
                    mxf = '-ds %s' % parameters.get('downsample_factor')
                    mne_mxf = ''
                    string = 'dsfactor-%s_' % \
                        parameters.get('downsample_factor')
                else:
                    print('downsampling factor must be an INTEGER greater than 1')
            elif not param:
                mxf = ''
                mne_mxf = ''
                string=''
            else:
                print('faulty "downsampling" setting')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _ds = set_ds(parameters.get('downsample'))

        def set_corr(param=None):
            if param:
                mxf = '-corr %s' % param
                mne_mxf = '--corr=%s' % param
                string = 'corr %s_' % \
                    round(float(param)*100)
            elif not param:
                mxf = ''
                mne_mxf= ''
                string=''
            else:
                print('faulty "correlation" setting (must be between 0 and 1)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _corr = set_corr(parameters.get('correlation'))

        # set linefreq according to wishes above and abort if set incorrectly
        def set_linefreq(param=None):
            if param:
                mxf = '-linefreq %s' % parameters.get('linefreq_Hz')
                mne_mxf = '--linefreq %s' % parameters.get('linefreq_Hz')
                string = 'linefreq-%s_' % parameters.get('linefreq_Hz')
            elif not param:
                mxf = ''
                mne_mxf = ''
                string = ''
            else:
                print('faulty "apply_linefreq" setting')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _linefreq = set_linefreq(parameters.get('apply_linefreq'))

        # Set autobad parameters
        def set_autobad(param=None):
            if param:
                mxf = '-autobad %s -badlimit %s' % (param, parameters.get('badlimit'))
                mne_mxf = '--autobad=%s' % parameters.get('badlimit')
                string = 'autobad_%s' % param
            elif not param:
                mxf = '-autobad %s' % param
                mxf = '--autobad %s' % param
                string = ''
            else:
                print('faulty "autobad" setting')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _autobad = set_autobad(parameters.get('autobad'))

        def set_bad_channels(param=None):
            if param:
                if isinstance(param, list):
                    bad_ch = ' '.join(param)
                else:
                    bad_ch = param
                mxf = '-bad %s' % bad_ch
                mne_mxf = '--bad %s' % bad_ch
                string = '_bad_%s' % bad_ch
            elif not param:
                mxf = ''
                mne_mxf= ''
                string=''
            else:
                print('faulty "bad_channels" setting (must be comma separated list)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _bad_channels = set_bad_channels(parameters.get('bad_channels'))

        tsss_default = parameters.get('tsss_default')
        
        if task in parameters.get('sss_files'):
            tsss_default = False

        def set_bids_proc():
            proc = []
            if tsss_default:
                proc.append(_tsss.string)
                if parameters.get('correlation'):
                    proc.append(f'corr{round(float(parameters.get('correlation'))*100)}')
            else:
                proc.append('sss')

            if parameters.get('movecomp_default'):
                proc.append(_mc.string)
            
            if 'continous' in trans_option and task in parameters.get('trans_conditions'):
                proc.append(_trans.string)
            
            proc = [p for p in proc if p != '']

            return('+'.join(proc))
        _proc = set_bids_proc()
        
        _merge_runs = parameters.get('merge_runs')
        _additional_cmd = parameters.get('MaxFilter_commands')

        self._trans = _trans
        self._force = _force
        self._cal = _cal
        self._ctc = _ctc
        self._ds = _ds
        self._tsss = _tsss
        self._corr = _corr
        self._mc = _mc
        self._autobad = _autobad
        self._bad_channels = _bad_channels
        self._linefreq = _linefreq
        self._proc = _proc
        self._merge_runs = _merge_runs
        self._additional_cmd = _additional_cmd

    def run_command(self, subject, session):
        """
        Execute MaxFilter processing for all tasks in a subject/session.
        
        Main processing function that handles complete MaxFilter workflow:
        1. Identifies eligible files and organizes by task
        2. Creates head position files for transformation tasks
        3. Configures task-specific parameters
        4. Executes MaxFilter commands with proper logging
        5. Manages file naming and output organization
        
        Processing Features:
        - Task-based file organization and processing
        - Automatic head position file generation
        - BIDS-compatible output naming with processing suffixes
        - Comprehensive logging with individual file logs
        - Skip processing for existing output files
        - Handles both standard and expert parameter sets
        
        Args:
            subject (str): Subject directory name
            session (str): Session directory name
        
        Returns:
            None
            
        Side Effects:
            - Creates processed FIF files with descriptive suffixes
            - Generates individual log files for each processed file
            - Creates head position and transformation files
            - Executes system calls to Elekta MaxFilter
            - Logs all processing steps and file operations
        
        File Naming Convention:
            Input: {task}_raw.fif
            Output: {task}_proc-{processing_string}_meg.fif
            Where processing_string describes applied corrections
        
        Error Handling:
            - Skips missing files with informative messages
            - Continues processing if individual files fail
            - Logs all subprocess calls and outputs
        """

        parameters = self.parameters
        
        debug = parameters.get('debug', False)

        data_root = parameters.get('data_path')
        output_path = parameters.get('out_path')
        # Check if output path is set
        if not output_path:
            output_path = data_root
 
        subj_in = f'{data_root}/{subject}/{session}/triux'
        subj_out = f'{output_path}/{subject}/{session}/triux'
        
        # Create log directory if it doesn't exist
        os.makedirs(f'{subj_out}/{'log'}', exist_ok=True)
        
        maxfilter_path = parameters.get('maxfilter_version')

        # List all files in directory
        all_fifs = sorted(glob('*.fif', root_dir=subj_in))

        # Create patterns to exclude files
        
        naming_convs = [
            'raw',
            'meg'
        ]
        naming_conv = re.compile(r'|'.join(naming_convs))
        
        trans_files = parameters.get('trans_conditions')
        sss_files = parameters.get('sss_files')
        empty_room_files = parameters.get('empty_room_files')

        if isinstance(trans_files, str):
            trans_files = [trans_files]
        if isinstance(sss_files, str):
            sss_files = [sss_files]
        if isinstance(empty_room_files, str):
            empty_room_files = [empty_room_files]

        tasks_to_run = sorted(list(set(
            trans_files +
            sss_files +
            empty_room_files)))
        
        # Remove if empty
        tasks_to_run = [t for t in tasks_to_run if t != '']

        for task in tasks_to_run:

            files = match_task_files(all_fifs, task)
            
            if not files:
                print(f'No files found for task: {task}')
                continue
            
            print(f'''
                Processing task: {task}
                Using files: 
                    {'\n'.join(files)}
                ''')

            # Average head position
            if task in trans_files:
                self.create_task_headpos(subj_in, subj_out, task, files, overwrite=False)

            self.set_params(subject, session, task)
            
            _proc = self._proc
            
            for file in files:

                clean = file.replace('.fif', f'_proc-{_proc}.fif')
                ncov = naming_conv.search(clean)
                
                if not ncov:
                    clean = clean.replace('.fif', '_meg.fif')

                # Use absolute path
                file = f"{subj_in}/{file}"
                clean = f"{subj_out}/{clean}"
                log = f'{subj_out}/{'log'}/{basename(clean).replace(".fif",".log")}'

                command_list = []
                command_list.extend([
                    maxfilter_path,
                    '-f %s' % file,
                    '-o %s' % clean,
                    self._cal.mxf,
                    self._ctc.mxf,
                    self._trans.mxf,
                    self._tsss.mxf,
                    self._ds.mxf,
                    self._corr.mxf,
                    self._mc.mxf,
                    self._autobad.mxf,
                    self._bad_channels.mxf,
                    self._linefreq.mxf,
                    self._force,
                    self._additional_cmd,
                    '-v',
                    '| tee -a %s' % log
                    ])
                self.command_mxf = ' '.join(command_list)
                self.command_mxf = re.sub(r'\\s+', ' ', self.command_mxf).strip()

                if not exists(clean):
                    print('''
                          Running Maxfilter on
                          Subject: %s
                          Session: %s
                          Task: %s
                          ''' % (subject, 
                                 session,
                                 task))
                    if not debug:
                        subprocess.run(self.command_mxf, shell=True, cwd=subj_in)
                        log(f'{file} -> {clean}')

                    else:
                        print(self.command_mxf)

                else:
                    print('''
                        Existing file: %s
                        Delete to rerun MaxFilter process
                        ''' % clean)

    def loop_dirs(self, max_workers=4):
        """
        Process multiple subjects and sessions in parallel.
        
        Orchestrates MaxFilter processing across entire dataset using parallel
        execution for efficiency. Handles subject filtering, session discovery,
        and error management for large-scale processing.
        
        Processing Workflow:
        1. Scan data directory for subjects (sub-* or NatMEG*)
        2. Filter subjects based on skip list
        3. Discover sessions within each subject directory
        4. Create (subject, session) task pairs
        5. Execute processing in parallel using ThreadPoolExecutor
        6. Handle exceptions and continue processing on failures
        
        Args:
            max_workers (int): Maximum number of parallel processes (default: 4)
        
        Returns:
            None
            
        Side Effects:
            - Processes entire dataset in parallel
            - Creates all output files and logs
            - Prints progress and error messages
            - Continues processing despite individual failures
        
        Performance Notes:
            - Uses ThreadPoolExecutor for I/O-bound MaxFilter calls
            - Scales processing to available CPU cores
            - Memory usage scales with max_workers
            - Network/disk I/O may be bottleneck for large datasets
        
        Error Handling:
            - Captures and reports exceptions for individual sessions
            - Continues processing remaining sessions on failure
            - Logs all subprocess errors and completion status
        """
        parameters = self.parameters
        data_root = parameters.get('data_path')
        
        subjects = sorted([s for s in glob('*', root_dir=data_root) if os.path.isdir(f'{data_root}/{s}') and (s.startswith('sub') or s.startswith('NatMEG'))])
        skip_subjects = parameters.get('subjects_to_skip')

        if not isinstance(skip_subjects, list):
            skip_subjects = [skip_subjects] if skip_subjects else []
        
        if skip_subjects:
            print(f'Skipping {", ".join(skip_subjects)}')
        
        subjects = [s for s in subjects if file_contains(s, skip_subjects)]

        # Collect all (subject, session) pairs
        subs_and_sess = []
        for subject in subjects:
            sessions = [s for s in sorted(glob('*', root_dir=f'{data_root}/{subject}')) if isdir(f'{data_root}/{subject}/{s}')]
            for session in sessions:
                subs_and_sess.append((subject, session))
        
        # Run in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.run_command, subject, session) for subject, session in subs_and_sess]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error in parallel task: {e}")

def args_parser():
    """
    Parse command-line arguments for MaxFilter script execution.
    
    Defines command-line interface with configuration file option for
    standalone script usage outside of pipeline integration.
    
    Returns:
        argparse.Namespace: Parsed arguments containing config file path
    """
    parser = argparse.ArgumentParser(description=
                                     '''Maxfilter
                                     
                                     Will use a configuation file to run MaxFilter on the data.
                                     Select to open an existing configuration file or create a new one.
                                     
                                     ''',
                                     add_help=True,
                                     usage='maxfilter [-h] [-c CONFIG]')
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    args = parser.parse_args()
    return args

# %%
def main(config=None):
    """
    Main entry point for MaxFilter processing pipeline.
    
    Coordinates complete MaxFilter workflow:
    1. Loads configuration from file or parameter
    2. Initializes MaxFilter processor with validated parameters
    3. Executes parallel processing across all subjects/sessions
    4. Handles configuration file selection and validation
    
    Args:
        config (dict, optional): Configuration dictionary. If None, loads
                                from command-line arguments or GUI selection
    
    Returns:
        None
        
    Side Effects:
        - Executes complete MaxFilter processing pipeline
        - Creates all processed files with SSS/tSSS corrections
        - Generates head position and transformation files
        - Produces movement plots for quality control
        
    Raises:
        SystemExit: If no configuration file provided or invalid config
    
    Usage Examples:
        # Command line with config file
        python maxfilter.py -c config.yml
        
        # Programmatic usage
        from maxfilter import main
        main(config_dict)
    """
    if config is None:
        args = args_parser()
        config_file = args.config
        if not config_file or not os.path.exists(config_file):
            config_file = askForConfig()
        if config_file:
            config = get_parameters(config_file)
            print(f'Using configuration file: {config_file}')
        else:
            print('No configuration file provided. Please provide a valid configuration file with -c or --config option.')
            return

    mf = MaxFilter(config)
    mf.loop_dirs()

if __name__ == "__main__":
    main()
