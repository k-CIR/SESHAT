"""
Author: C Pfeiffer & Andreas Gerhardsson (adapted from script by T Cheung)
Last Modified June 2025
Function for adding dev_to_head_trans to an OPM-MEG recording

This script performs HPI coregistration for OPM-MEG data by:
1. Localizing HPI coils in device coordinates using sequential activation
2. Computing coordinate transformations between device and head space
3. Applying transformations to MEG recordings for head localization

The pipeline processes subjects and sessions automatically, using parallel
processing for efficiency. It requires configuration files specifying
OPM parameters, HPI frequencies, and file patterns.

Dependencies:
- MNE-Python for MEG data processing
- scipy for signal processing and spatial operations
- concurrent.futures for parallel processing
- PyYAML for configuration management

Usage:
    python add_hpi.py -c config.yml
"""
import sys
import argparse
import os
import re
from glob import glob
import json
import yaml
import numpy as np
import matplotlib.pyplot as plt
from typing import Union
import mne

import concurrent.futures
from functools import partial
from tqdm import tqdm
from mne._fiff.pick import pick_types


from mne.transforms import apply_trans
from opm_utility_scripts.channels import find_zero_location_channels, get_hpi_output_channels
from opm_utility_scripts.viz import plot_3d, plot_psd
from opm_utility_scripts import load_datafile, load_polhemus, select_best_hpi_file
from opm_utility_scripts.io import write_bw_marker_file
from opm_utility_scripts.analog.mapping import generate_analog_channel_mapping
from opm_utility_scripts.analog.rename import rename_channels
from opm_utility_scripts.hpi._core import apply_transform

from utils import (
    log, configure_logging,
    askForConfig,
    file_contains,
    noise_patterns,
    proc_patterns
)

###############################################################################
# Utility Functions
###############################################################################
global VERBOSE

def configure_verbosity(verbose: bool):
    """
    Configure verbosity for the script.

    Args:
        verbose (bool): If True, enable detailed print statements. Otherwise, suppress them.
    """
    global VERBOSE
    VERBOSE = verbose

def verbose_print(message: str):
    """
    Log a message if verbosity is enabled.

    Args:
        message (str): The message to log.
    """
    if VERBOSE:
        print(message)

# write_bw_marker_file, find_zero_location_channels (TC_findzerochans),
# get_hpi_output_channels (TC_get_hpiout_names), plot_psd (tc_plot_psd),
# and plot_3d were previously defined here. They are now imported from
# opm_utility_scripts above.

###############################################################################
# Configuration and Setup Functions
###############################################################################

def get_parameters(config:str):
    """
    Load and parse HPI processing configuration from YAML file.
    
    Extracts OPM-specific and project parameters needed for HPI coregistration
    including coil frequencies, file patterns, and processing options.
    
    Args:
        config_file (str): Path to YAML configuration file
    
    Returns:
        dict: Configuration dictionary with keys:
            - tasks: List of experimental tasks
            - polhemus_file: Pattern for Polhemus digitization files
            - opmMEG: OPM MEG data directory
            - hpinames: HPI coil naming patterns
            - hpifreq: HPI coil frequency (default: 33.0 Hz)
            - downsample_freq: Target sampling frequency (default: 1000 Hz)
            - overwrite: Whether to overwrite existing files
            - plot: Whether to generate visualization plots
    """
    
    if isinstance(config, str):
        if config.endswith('.json'):
            with open(config, 'r') as f:
                config = json.load(f)
        elif config.endswith('.yml') or config.endswith('.yaml'):
            with open(config, 'r') as f:
                config = yaml.safe_load(f)
        else:
            raise ValueError("Unsupported configuration file format. Use .json or .yml/.yaml")
    
    hpi_config = {
        'tasks': config.get('Project', {}).get('Tasks', []),
        'rename_analog_channels': config.get('OPM', {}).get('rename_analog_channels', False),
        'polhemus_file': config.get('OPM', {}).get('polhemus', ''),
        'opmMEG': config.get('Project', {}).get('Raw', ''),  # Use Raw directory path
        'hpinames': config.get('OPM', {}).get('hpi_names', ''),
        'hpifreq': config.get('OPM', {}).get('frequency', 33.0),
        'downsample_freq': config.get('OPM', {}).get('downsample_to_hz', 1000),
        'overwrite': config.get('OPM', {}).get('overwrite', False),
        'plot': config.get('OPM', {}).get('plot', False),
        'logfile': config.get('Project', {}).get('Logfile', '')
    }
    return hpi_config
     
def find_hpi_fit(config, subject, session, overwrite=False):
    """
    Localize HPI coils in device coordinates using sequential activation.
    
    Main HPI localization function that:
    1. Finds HPI and Polhemus files for the session
    2. Processes HPI activation signals to extract coil locations
    3. Fits magnetic dipoles to determine device coordinates
    4. Establishes coordinate transformation using fiducial points
    
    Processing Steps:
    - Loads HPI activation recording and removes bad/zero channels
    - Extracts HPI output channel signals and frequencies
    - Crops data to HPI activation windows using peak detection
    - Computes HPI amplitudes and locations for each coil
    - Uses Polhemus fiducials to establish head coordinate system
    
    Args:
        config (dict): Configuration dictionary with parameters
        subject (str): Subject identifier (e.g., 'sub-001')
        session (str): Session identifier (e.g., '20250127')
        overwrite (bool): Force reprocessing of existing files
    
    Returns:
        dict: {hedscan_files, hpi_dev, hpi_gofs, hpi_orig, hpi_names, 
                pol_info, nasion, lpa, rpa, raw, new_sfreq}
            - hedscan_files (list): Files requiring HPI transformation
            - hpi_dev (np.ndarray): HPI locations in device coordinates
            - hpi_gofs (np.ndarray): Goodness of fit for each coil (0-1)
            - hpi_orig (np.ndarray): HPI locations in head coordinates
            - hpi_names (list): HPI coil channel names
            - pol_info (dict): Polhemus digitization information
            - nasion, lpa, rpa (np.ndarray): Fiducial point coordinates
            - raw (mne.io.Raw): Processed HPI data
            - new_sfreq (bool): Whether data was resampled
    
    Side Effects:
        - Logs processing steps and coil fit quality
        - Modifies raw data sampling frequency if needed
        - Removes bad and zero-location channels
    
    Notes:
        - Requires minimum 3 HPI coils for head localization
        - Uses 2-second data windows for dipole fitting
        - Peak detection finds HPI activation periods
        - Goodness of fit >0.9 indicates reliable coil localization
    """
    
    opmMEGdir = config.get('opmMEG')
    hpinames = config.get('hpinames')
    hpifreq = config.get('hpifreq', 33.0)
    new_sfreq = config.get('downsample_freq', 1000)
    hpinames=config.get('hpinames')
    exclude_patterns = [r'-\d+\.fif', '_trans', 'avg.fif', 'hpi']
    overwrite = config.get('overwrite', False)
    logfile = config.get('logfile', 'pipeline_log.log')
    
    log_path = opmMEGdir.replace('raw', 'logs')
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    configure_logging(log_dir=log_path, log_file=logfile)

    # Check if all hedscan files have been processed
    all_files = sorted(glob(f'{opmMEGdir}/{subject}/{session}/hedscan/*.fif'))

    hedscan_files = [f for f in all_files if not file_contains(f, hpinames + noise_patterns + proc_patterns + exclude_patterns)]

    new_hedscan_files = []
    for file in hedscan_files:
        sfreq = load_datafile(file)['sfreq']

        proc = 'proc-hpi'
        if new_sfreq and not (int(new_sfreq) == int(sfreq)):
            proc += f'+ds'
        proc += f'_raw'
        if not os.path.exists(file.replace('raw.fif', proc + '.fif')):
            new_hedscan_files.append(file)
    
    hpi_fit_parameters = {
        'hedscan_files': [],
        'hpi_dev': None,
        'hpi_gofs': None,
        'hpi_orig': None,
        'hpi_names': None,
        'pol_info': None,
        'nasion': None,
        'lpa': None,
        'rpa': None,
        'raw': None,
        'new_sfreq': None
    }

    if not overwrite:
        hedscan_files = new_hedscan_files
    if overwrite or hedscan_files:
        log("HPI", f"Processing {subject}/{session}", 'info',logfile=logfile, logpath=log_path)
        # Stage 1: new polhemus/ subdir (JSON and FIF), subject + session must appear in filename.
        # If multiple files match, use the most recent by timestamp embedded in the filename
        # (e.g. digitisation_sub-0009_20260811144612.json — 14-digit YYYYMMDDHHMMSS suffix).
        polhemus_dir = f"{opmMEGdir}/{subject}/{session}/polhemus"
        polfile_list = []
        if os.path.isdir(polhemus_dir):
            candidates = []
            for f in glob(f"{polhemus_dir}/*"):
                fname = os.path.basename(f)
                if subject in fname and session in fname:
                    if f.endswith('.json') or f.endswith('.fif'):
                        # Extract the numeric timestamp from the filename for sorting.
                        # Filenames carry a 14-digit YYYYMMDDHHMMSS stamp; fall back to
                        # the full filename string so lexicographic order is preserved
                        # even for files with shorter or absent numeric suffixes.
                        ts_match = re.search(r'(\d{14})', fname)
                        sort_key = ts_match.group(1) if ts_match else fname
                        candidates.append((sort_key, f))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                polfile_list = [candidates[-1][1]]  # most recent only

        # Stage 2: legacy triux/ fallback (existing logic, unchanged)
        if not polfile_list:
            polhemus_patterns = config['polhemus_file']
            if isinstance(polhemus_patterns, str):
                polhemus_patterns = [polhemus_patterns]
            polfile_list = [
                file for pattern in polhemus_patterns + [f for f in config['tasks'] if f not in polhemus_patterns]
                for file in glob(f"{opmMEGdir}/{subject}/{session}/triux/*{pattern.replace('.fif', '')}*.fif")
            ]
            polfile_list = [f for f in polfile_list if not file_contains(f, exclude_patterns + noise_patterns)]

        if not polfile_list:
            log("HPI", f"No polhemus file found matching: {polfile_list}", 'error',logfile=logfile, logpath=log_path)
            polfile = None
            return hpi_fit_parameters

        hpi_files = [f for f in all_files if file_contains(f, hpinames)]
        if not hpi_files:
            log("HPI", f"No hpi file found matching: {hpinames}", 'error',logfile=logfile, logpath=log_path)
            hpifile = None
            return hpi_fit_parameters
        pol = None
        for pf in polfile_list:
            try:
                pol = load_polhemus(pf)
                verbose_print(f"Using polhemus: {pf}")
                break
            except Exception as e:
                log("HPI", f"Error reading {pf}: {e}", 'error', logfile=logfile, logpath=log_path)

        if pol is None:
            log("HPI", "No valid polhemus file found.", 'error', logfile=logfile, logpath=log_path)
            return hpi_fit_parameters

        try:
            best_hpi_path, fit = select_best_hpi_file(hpi_files, pol, hpifreq)
            gofs = fit['hpi_gofs']
            high_gofs = gofs[gofs > 0.9]
            mean_gof = np.mean(high_gofs) if len(high_gofs) else np.mean(gofs)
            verbose_print(f"Best HPI file: {best_hpi_path} (mean GOF {mean_gof:.3f})")
        except RuntimeError as e:
            log("HPI", str(e), 'error', logfile=logfile, logpath=log_path)
            return hpi_fit_parameters

        try:
            verbose_print('**** HPI fit complete — building parameter dict ***')
            hpi_fit_parameters['hedscan_files'] = hedscan_files
            hpi_fit_parameters['hpi_dev']    = fit['hpi_dev']
            hpi_fit_parameters['hpi_gofs']   = fit['hpi_gofs']
            hpi_fit_parameters['hpi_orig']   = fit['hpi_orig']
            hpi_fit_parameters['hpi_names']  = fit['hpi_names']
            hpi_fit_parameters['pol_info']   = pol
            hpi_fit_parameters['nasion']     = fit['nasion']
            hpi_fit_parameters['lpa']        = fit['lpa']
            hpi_fit_parameters['rpa']        = fit['rpa']
            hpi_fit_parameters['fit']        = fit   # full fit dict passed to process_single_file
            hpi_fit_parameters['new_sfreq']  = new_sfreq
            hpi_fit_parameters['logfile']    = logfile
            hpi_fit_parameters['log_path']   = log_path
        except Exception as e:
            log("HPI", f"Error building HPI parameter dict: {e}", 'error', logfile=logfile, logpath=log_path)
    else:
        log("HPI", 'No (new) files to process', 'info', logfile=logfile, logpath=log_path)

    return hpi_fit_parameters

def process_single_file(datfile, hpi_fit_parameters: dict, plotResult, log_path, rename_analog):
    """
    Apply HPI-derived coordinate transformation to an individual MEG file.

    Orchestrates file-level concerns (output-filename construction, skip-if-exists
    check, bad-channel safety thresholds, analog channel renaming, 3-D plot) and
    delegates the core transform/save step to
    :func:`opm_utility_scripts.hpi._core.apply_transform`.

    Args:
        datfile (str): Path to the raw MEG file to transform.
        hpi_fit_parameters (dict): Parameters produced by :func:`find_hpi_fit`.
            Required keys: ``fit`` (full fit dict from ``fit_hpi``),
            ``hpi_names``, ``new_sfreq``, ``logfile``, ``log_path``, ``overwrite``.
        plotResult (bool): Whether to generate a 3-D visualisation after saving.
        log_path (str): Directory for log files.
        rename_analog (bool): Whether to rename analog channels after saving.
    """
    path = os.path.dirname(datfile)
    stem = os.path.splitext(os.path.basename(datfile))[0].replace('_raw', '')

    fit        = hpi_fit_parameters['fit']
    hpi_names  = hpi_fit_parameters['hpi_names']
    new_sfreq  = hpi_fit_parameters['new_sfreq']
    logfile    = hpi_fit_parameters['logfile']
    log_path   = hpi_fit_parameters['log_path']
    overwrite  = hpi_fit_parameters.get('overwrite', False)

    configure_logging(log_dir=log_path, log_file=logfile)

    # Build the output filename with the same dynamic suffix as before.
    sfreq = mne.io.read_info(datfile, verbose='error').get('sfreq', None)
    proc  = 'proc-hpi'
    if new_sfreq and not (int(new_sfreq) == int(sfreq)):
        proc += '+ds'
    proc += '_raw'
    suffix   = f'_{proc}.fif'
    savename = stem + suffix                        # just the basename stem + suffix
    outpath  = os.path.join(path, savename)

    if not overwrite and os.path.exists(outpath):
        verbose_print(f"Skipping {savename} (already exists)")
        return

    try:
        # Pre-flight bad-channel check so we can abort before the expensive fit.
        raw_check = mne.io.read_raw_fif(datfile, preload=False, verbose='error')
        bads = find_zero_location_channels(raw_check.info)
        if len(bads) > 100:
            log("HPI", f"Found {len(bads)} bad channels. Check recording.", 'error',
                logfile=logfile, logpath=log_path)
            return
        if len(bads) > 9:
            log("HPI", f"Found {len(bads)} bad channels", 'warning',
                logfile=logfile, logpath=log_path)

        # Core load / transform / save — delegated to the shared implementation.
        # apply_transform handles: load, resample, drop bads+zerochans, embed
        # digitisation, update dev_head_t, and save.
        saved_path = apply_transform(datfile, fit, new_sfreq, suffix)

        # Optional: rename analog channels in the saved file.
        if rename_analog:
            mapping = generate_analog_channel_mapping()
            verbose_print('Renaming analog channels using mapping')
            verbose_print(f'{mapping}')
            rename_channels(saved_path, mapping, saved_path)

        # Fit quality report.
        hpi_dev    = fit['hpi_dev']
        hpi_gofs   = fit['hpi_gofs']
        hpi_orig   = fit['hpi_orig']
        dist       = fit['dist']
        dev_to_head_trans = fit['dev_to_head_trans']
        hpi_head   = apply_trans(dev_to_head_trans, hpi_dev)

        msg_coils = ''
        for idx, value in enumerate(hpi_gofs):
            status = 'ok' if value > 0.9 else 'not ok'
            msg_coils += f"Coil: {hpi_names[idx][-3:]}, GOF: {value:.3f}, Status: {status}\n"

        verbose_print(f'''---------------------------------------------
        hpi_orig: {hpi_orig}
        hpi_dev:  {hpi_dev}
        mean distance = {np.mean(dist) * 1000:.1f} mm
        {msg_coils}        ---------------------------------------------''')

        if plotResult:
            raw_plot = mne.io.read_raw_fif(saved_path, preload=False, verbose='error')
            senspos = np.array([], dtype=float)
            picks = pick_types(raw_plot.info, meg='mag')
            for j in picks:
                senspos = np.append(senspos,
                    apply_trans(dev_to_head_trans, raw_plot.info['chs'][j]['loc'][0:3]))
            n = int(senspos.shape[0] / 3)
            senspos = senspos.reshape((n, 3))

            senslabel = []
            for j in picks:
                idx = raw_plot.info['chs'][j]['ch_name'].find('s')
                senslabel.append(raw_plot.info['chs'][j]['ch_name'][idx:] if idx != -1 else '')

            digpts = np.array([], dtype=float)
            for j in raw_plot.info['dig']:
                digpts = np.append(digpts, j['r'])
            n = int(digpts.shape[0] / 3)
            digpts = digpts.reshape((n, 3))

            hpilabel = [str(j + 1) for j in range(len(hpi_names))]
            plot_params = {
                'senspos': senspos,
                'senslabel': senslabel,
                'hpipos': hpi_orig,
                'hpilabel': hpilabel,
                'hpipos2': hpi_head,
                'hpilabel2': hpi_names,
                'digpos': digpts,
            }
            plot_3d(plot_params, saved_path.replace('_raw.fif', '_3d_plot.png'))

    except Exception as e:
        log("HPI", f"Error occurred while processing {savename}: {e}", 'error',
            logfile=logfile, logpath=log_path)

###############################################################################
# Command Line Interface
###############################################################################

def args_parser():
    """
    Parse command-line arguments for HPI coregistration script.
    
    Defines command-line interface with configuration file option for
    standalone script execution.
    
    Returns:
        argparse.Namespace: Parsed arguments with config file path
    """
    parser = argparse.ArgumentParser(description='Add HPI to OPM-MEG recordings.')
    parser.add_argument('-c', '--config', type=str, default='config.yml',
                        help='Path to the configuration file (default: config.yml)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    return parser.parse_args()

def main(config: Union[str, dict]=None):
    """
    Main execution function for HPI coregistration pipeline.
    
    Orchestrates the complete HPI processing workflow:
    1. Loads configuration and validates parameters
    2. Scans for subjects and sessions requiring processing
    3. Performs HPI localization for each session
    4. Applies transformations to all relevant files
    5. Uses parallel processing for efficiency
    
    Processing Pipeline:
    - Iterates through all subjects in OPM MEG directory
    - Finds sessions with 6-digit date format (YYMMDD)
    - Calls find_hpi_fit() to localize HPI coils
    - Applies transformations to hedscan files in parallel
    - Handles errors and logs processing status
    
    Configuration Requirements:
    - opmMEG: Directory containing subject/session structure
    - hpinames: Patterns to identify HPI activation files
    - polhemus_file: Patterns for Polhemus digitization files
    - hpifreq: HPI coil driving frequency
    - Processing options: overwrite, plotting, downsampling
    
    Args:
        None (uses command-line arguments or GUI config selection)
    
    Returns:
        None
        
    Side Effects:
        - Processes all eligible MEG files with HPI transformation
        - Creates log files in data/log directory
        - Uses ProcessPoolExecutor for parallel file processing
        - Prints completion status
    
    Error Handling:
        - Continues processing if individual files fail
        - Logs all exceptions for debugging
        - Validates configuration file existence
    
    Performance:
        - Parallel processing scales with available CPU cores
        - ProcessPoolExecutor handles memory-intensive operations
        - Shared parameter passing via functools.partial
    """
    

    if config is None:
        # Parse command line arguments
        args = args_parser()
        
        if args.config:
            config_file = args.config
        else:
            config_file = askForConfig()
        
        if config_file:
            config = get_parameters(config_file)
        
        else:
            print('No configuration file selected')
            sys.exit(1)
    elif isinstance(config, str):
        config_file = config
        config = get_parameters(config_file)

    opmMEGdir = config.get('opmMEG')
    overwrite = config.get('overwrite', False)
    plotResult = config.get('plot', False)
    rename_analog = config.get('rename_analog_channels', False)

    log_path = opmMEGdir.replace('raw', 'logs')
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    logfile = config.get('logfile', 'adding_hpi.log')
    configure_logging(log_dir=log_path, log_file=logfile)
    
    subjects = sorted([subject for subject in glob('sub-*',
                                                root_dir = f'{opmMEGdir}')
                    if os.path.isdir(f'{opmMEGdir}/{subject}')])
    subjects_to_process = len(subjects)
    count = 0
    pbar = tqdm(total=subjects_to_process, 
                desc=f"Processing files", 
                unit=" file(s)",
                disable=not sys.stdout.isatty(),
                ncols=80,
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
    
    for subject in subjects:
        sessions = sorted([
            session for session in glob('*', root_dir = f'{opmMEGdir}/{subject}')
            if os.path.isdir(f'{opmMEGdir}/{subject}/{session}') and re.match(r'^\d{6}$', session)
        ])
        for session in sessions:
            hpi_fit_parameters = find_hpi_fit(config, subject, session, overwrite=overwrite)

            hedscan_files = hpi_fit_parameters.get('hedscan_files', [])
            # Create partial function with shared parameters
            if overwrite or hedscan_files:
                try:
                    process_func = partial(
                        process_single_file,
                        hpi_fit_parameters=hpi_fit_parameters,
                        plotResult=plotResult,
                        log_path=log_path,
                        rename_analog=rename_analog
                )
                    pbar.update(1)
                    print(f'{count}/{len(hedscan_files)} files to process')
                except Exception as e:
                    log("HPI", f"Error occurred while processing: {e}", 'error', logfile=logfile, logpath=log_path)
                

                # Use ThreadPoolExecutor or ProcessPoolExecutor
                with concurrent.futures.ProcessPoolExecutor(max_workers=len(hedscan_files)*2) as executor:
                    # Submit all tasks and get future objects
                    futures = [executor.submit(process_func, datfile) for datfile in hedscan_files]
                    
                    # Wait for all tasks to complete and handle any exceptions
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            future.result()  # This will raise an exception if the task failed
                        except Exception as exc:
                            log("HPI", f'Task generated an exception: {exc}', 'error',logfile=logfile, logpath=log_path)
        count += 1
        print(f'Completed {count}/{subjects_to_process} subjects')
        pbar.update(1)
    pbar.close()

    log("HPI", "OPM preprocessing completed successfully.", 'info',logfile=logfile, logpath=log_path)
    return True

# Ensure VERBOSE is defined globally at the top of the script
VERBOSE = False

# Use concurrent.futures instead of multiprocessing
if __name__ == '__main__':
    args = args_parser()
    configure_verbosity(args.verbose)
    main(config=args.config)

