from glob import glob
from mne.io import read_raw, read_info
from mne._fiff.write import _get_split_size
import re
import json
import argparse
import yaml
from copy import deepcopy
import os
from os.path import basename, exists, isdir, getmtime, getsize, join, dirname
from shutil import copy2, copytree
from typing import Union
from datetime import datetime
import filecmp
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
from tqdm import tqdm

calibration = '/neuro/databases/sss/sss_cal.dat'
crosstalk = '/neuro/databases/ctc/ct_sparse.fif'

from utils import (
    log, configure_logging,
    headpos_patterns,
    proc_patterns,
    file_contains,
    askForConfig
)

global local_dir

def get_parameters(config: Union[str, dict]) -> dict:
    """Reads a configuration file and returns a dictionary with the parameters.
    
    Or extracts the parameters from a configuration dict.
    
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
    
    copy_config = deepcopy(config_dict['Project'])
    
    return copy_config

def copy_if_newer_or_larger(source, destination):
    """
    Copy file from source to destination if source is newer or larger than destination.
    """
    if not exists(destination):
        if isdir(source):
            copytree(source, destination)
        else:
            copy2(source, destination)
    elif (getmtime(source) > getmtime(destination) or
    getsize(source) > getsize(destination)):
        if isdir(source):
            copytree(source, destination, dirs_exist_ok=True)
        else:
            copy2(source, destination)

def check_fif(source, destination):

    raw_src = read_raw(source, allow_maxshield=True, verbose='error')
    raw_dst = read_raw(destination, allow_maxshield=True, verbose='error')
    
    info_src = raw_src.info
    info_dst = raw_dst.info

    checks = {
        # 'times': (raw_src.times == raw_dst.times).all(),
        'meas_id_version': info_src['meas_id']['version'] == info_dst['meas_id']['version'],
        'secs': info_src['meas_id']['secs'] == info_dst['meas_id']['secs'],
        'size': info_src.__sizeof__() == info_dst.__sizeof__(),
        'date': info_src['meas_date'] == info_dst['meas_date'],
        'sfreq': info_src['sfreq'] == info_dst['sfreq'],
    }

    not_compare = [c for c in checks if not checks[c]]

    if all(checks.values()) and not not_compare:
        return True, [str(f) for f in raw_src.filenames][0], [str(f) for f in raw_dst.filenames]

    else:
        print(f'The following checks failed: {not_compare}')
        return False, [str(f) for f in raw_src.filenames][0], [str(f) for f in raw_dst.filenames]

def check_size_fif(source, split_size='2GB'):
    raw_size = getsize(source)
        
    # print(f'{basename(source)}: {round(raw_size / 1e9, 2)} GB')
    if raw_size > _get_split_size(split_size):
        return True
    else:
        return False

def is_binary(file_path):
    """Check if a file is binary by reading a chunk of it."""
    with open(file_path, 'rb') as f:
        chunk = f.read(1024)  # Read first 1KB
        return b'\0' in chunk  # Binary files typically contain null bytes

def copy_squid_databases(config: dict):
    
    calibration_dest = config.get('Calibration', calibration)
    crosstalk_dest = config.get('Crosstalk', crosstalk)
    
    if calibration and exists(calibration):
        if not exists(dirname(calibration_dest)):
            os.makedirs(dirname(calibration_dest), exist_ok=True)    
        copy_if_newer_or_larger(calibration, calibration_dest)
    else:
        print(f'Calibration file {calibration} does not exist.')
    
    if crosstalk and exists(crosstalk):
        if not exists(dirname(crosstalk_dest)):
            os.makedirs(dirname(crosstalk_dest), exist_ok=True)
        copy_if_newer_or_larger(crosstalk, crosstalk_dest)
    else:
        print(f'Crosstalk file {crosstalk} does not exist.')

def check_match(source, destination):
    """
    Check if the file has been transferred correctly by comparing source and destination.
    For .fif files, use MNE to read and compare metadata.
    For other files, use filecmp.
    """
    match = False
    if not exists(destination):
        match = False
    
    if isdir(source):
        match = filecmp.dircmp(source, destination).funny_files == []
    # Check if fif file and size > 2GB, then expecting split and use check_fif
    if all([file_contains(basename(source), [r'\.fif$', r'\.fif']), check_size_fif(source)]):
        match, source, destination = check_fif(source, destination)
    else:
        match = filecmp.cmp(source, destination, shallow=False)

    return match, source, destination
    
def copy_data(source, destination, logfile=None, log_path=None):
    """
    Copy file from source to destination with intelligent handling of .fif files.
    
    Args:
        source: Source file path
        destination: Destination file path
        logfile: Optional log filename
        log_path: Optional log directory path
    """
    if exists(destination):
        return check_match(source, destination)
    else:
        # Create destination directory if it doesn't exist
        os.makedirs(dirname(destination), exist_ok=True)
        
        # Files are different, need to handle based on file type
        is_fif_file = file_contains(basename(source), [r'\.fif$', r'\.fif'])
        fif_2GB = check_size_fif(source)
        fif_except = not file_contains(basename(source), headpos_patterns + ['ave.fif', 'config.fif'])
        is_not_split = not file_contains(basename(source), [r'-\d+.fif'] + [r'-\d+_' + p for p in proc_patterns])
        
        if all([is_fif_file, fif_2GB, fif_except, is_not_split]):
            # Check if larger than 2GB
            try:
                raw = read_raw(source, allow_maxshield=True, verbose='error')
                raw.save(destination, overwrite=True, verbose='error')
                destination = [str(f) for f in 
                               read_raw(destination, allow_maxshield=True, verbose='error').filenames]
                if logfile and log_path:
                    log('Copy', f'Copied (split if > 2GB) {source} --> {destination}', 
                        logfile=logfile, logpath=log_path)
            except Exception as e:
                copy_if_newer_or_larger(source, destination)
                if logfile and log_path:
                    log('Copy', f'{source} --> {destination} {e}', 'warning',
                        logfile=logfile, logpath=log_path)
        else:
            # For non-fif files, use standard copy logic
            copy_if_newer_or_larger(source, destination)
            log('Copy', f'{source} --> {destination} {e}', 'warning',
                        logfile=logfile, logpath=log_path)

    return True, source, destination

def make_process_list(config, check_existing=False):
    local_dir = config['Raw']
    if not exists(local_dir):
        os.makedirs(local_dir, exist_ok=True)
            
    project_root = dirname(local_dir)
    log_path = join(project_root, 'log')
    os.makedirs(log_path, exist_ok=True)
    logfile = config.get('Logfile', 'pipeline_log.log')
    configure_logging(log_dir=log_path, log_file=logfile)
    
    sinuhe = config.get('Sinuhe raw', '')
    kaptah = config.get('Kaptah raw', '')
    
    files = []
    
    if sinuhe:
        natmeg_subjects  = [s for s in glob(f'NatMEG_*', root_dir=sinuhe) if isdir(f'{sinuhe}/{s}')]
        subjects = sorted(list(set([s.split('_')[-1] for s in natmeg_subjects])))
        other_files_and_dirs = [f for f in glob(f'*', root_dir=sinuhe) if f not in natmeg_subjects]

        for item in other_files_and_dirs:
            source = f'{sinuhe}/{item}'
            destination = f'{local_dir}/{item}'
            files.append((source, destination))

            # copy_file(source, destination, logfile=logfile, log_path=log_path)
        
        for subject in subjects:
            sessions = sorted([session for session in glob('*', root_dir = f'{sinuhe}/NatMEG_{subject}')
            if isdir(f'{sinuhe}/NatMEG_{subject}/{session}') and re.match(r'^\d{6}$', session)
            ])
            sinuhe_subject_dir = f'{sinuhe}/NatMEG_{subject}'
            local_subject_dir = f'{local_dir}/sub-{subject}'
            
            items = [f for f in glob(f'*', root_dir=sinuhe_subject_dir) if f not in sessions]
            for item in items:
                source = f'{sinuhe_subject_dir}/{item}'
                destination = f'{local_subject_dir}/{item}'
                files.append((source, destination))

                # copy_file(source, destination, logfile=logfile, log_path=log_path)
                
            for session in sessions:
                items = [f for f in glob(f'*', root_dir=f'{sinuhe_subject_dir}/{session}/meg')]
                for item in items:
                    source = f'{sinuhe_subject_dir}/{session}/meg/{item}'
                    destination = f'{local_dir}/sub-{subject}/{session}/triux/{item}'
                    files.append((source, destination))
                    # copy_file(source, destination, logfile=logfile, log_path=log_path)
    elif not isdir(sinuhe):
            log('Copy', f"{sinuhe} is not a directory", 'error', logfile=logfile, logpath=log_path)
    
    elif not glob('*', root_dir=sinuhe):
        log('Copy', f"{sinuhe} is empty", 'warning', logfile=logfile, logpath=log_path)
    else: 
        log('Copy', 'No TRIUX directory defined', 'warning', logfile=logfile, logpath=log_path)

    
    if kaptah:
        kaptah_subjects  = [s for s in glob(f'sub-*', root_dir=kaptah) if isdir(f'{kaptah}/{s}')]
        
        other_files_and_dirs = [f for f in glob(f'*', root_dir=kaptah) if f not in kaptah_subjects]
        
        subjects = sorted(list(set([s.split('-')[-1] for s in kaptah_subjects])))
        
        for item in other_files_and_dirs:
            source = f'{kaptah}/{item}'
            destination = f'{local_dir}/{item}'
            files.append((source, destination))
        
        for subject in subjects:

            all_files = glob(f'*', root_dir=f'{kaptah}/sub-{subject}')
            # Extract unique dates from session folder names (assuming date format in session name, e.g., '20240607')
            hedscan_dates = set()
            for session in all_files:
                match = re.search(r'(\d{8})', session)
                if match:
                    hedscan_dates.add(match.group(1)[2:])
            sessions = sorted(list(hedscan_dates))
            kaptah_subject_dir = f'{kaptah}/sub-{subject}'
            local_subject_dir = f'{local_dir}/sub-{subject}'
            
            # Copy any files not marked with a date
            items = [f for f in glob(f'*', root_dir=kaptah_subject_dir) 
                     if not any(f.startswith(f'20{session}') for session in sessions)]
            for item in items:
                source = f'{kaptah_subject_dir}/{item}'
                destination = f'{local_subject_dir}/{item}'
                files.append((source, destination))

            for session in sessions:
                
                items = sorted([f for f in glob(f'*', root_dir=kaptah_subject_dir) 
                     if any(f.startswith(f'20{session}') for session in sessions)])
                
                # Create a mapping of original to renamed files to handle files with task name at different times
                file_mapping = {}
                name_counts = {}

                for item in items:
                    if 'file-' in item:
                        prefix, suffix = item.split('file-', 1)
                        # Count occurrences of each suffix
                        name_counts[suffix] = name_counts.get(suffix, 0) + 1
                        
                        # Generate new name with duplicate numbering if needed
                        if name_counts[suffix] == 1:
                            new_name = suffix
                        else:
                            pre, post = suffix.rsplit('_', 1)
                            new_name = f"{pre}_dup{name_counts[suffix]}_{post}"
                        
                        file_mapping[item] = new_name
                
                for item in items:
                    source = f'{kaptah}/sub-{subject}/{item}'
                    # Clean filename
                    dst_item = file_mapping.get(item, item)
                    
                    destination = f'{local_dir}/sub-{subject}/{session}/hedscan/{dst_item}'
                    
                    files.append((source, destination))
    
    elif not isdir(kaptah):
            log('Copy', f"{kaptah} is not a directory", 'error', logfile=logfile, logpath=log_path)
    
    elif not glob('*', root_dir=kaptah):
        log('Copy', f"{kaptah} is empty", 'warning', logfile=logfile, logpath=log_path)
    else: 
        log('Copy', 'No Hedscan directory defined', 'warning', logfile=logfile, logpath=log_path)


    return files

def process_file_worker(file_info, logfile, log_path):
    """
    Worker function to process a single file transfer.
    
    Args:
        file_info: Tuple of (source, destination)
        logfile: Log filename
        log_path: Log directory path
    
    Returns:
        Tuple of (success, source, destination, message)
    """
    source, destination = file_info

    try:
        match_exists, source, destination = check_match(source, destination)
        if not match_exists:
            success, src, dst = copy_data(source, destination, logfile=logfile, log_path=log_path)
            msg = "Copy completed successfully"
            match = True
        else:
            msg = "File already up to date"
            match = True
    except Exception as e:
        msg = f"Error processing file: {str(e)}"
        match = False

    return match, source, destination, msg

def parallel_copy_files(config, max_workers=4):
    """
    Copy files in parallel using ThreadPoolExecutor.
    
    Args:
        config: Configuration dictionary
        max_workers: Maximum number of worker threads
    
    Returns:
        List of results from file processing
    """
    files = make_process_list(config)
    
    # Extract log configuration from config
    local_dir = config['Raw']
    project_root = dirname(local_dir)
    log_path = join(project_root, 'log')
    logfile = config.get('Logfile', 'pipeline_log.log')
    
    results = []
    successful_copies = 0
    failed_copies = 0
    
    # Use ThreadPoolExecutor for I/O bound operations like file copying
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_file_worker, file_info, logfile, log_path): file_info 
            for file_info in files
        }
        
        # Setup progress bar if tqdm is available

        progress_bar = tqdm(total=len(files), desc="Copying files", unit="file")
        
        # Process completed tasks
        for future in as_completed(future_to_file):
            file_info = future_to_file[future]
            try:
                success, source, destination, message = future.result()
                results.append((success, source, destination, message))

                if success:
                    successful_copies += 1
                else:
                    failed_copies += 1
                
                # Update progress bar
                status = "✓" if success else "✗"
                progress_bar.set_postfix({
                    'Success': successful_copies, 
                    'Failed': failed_copies,
                    'Current': f"{status} {basename(source)}"
                })
                progress_bar.update(1)
                    
            except Exception as exc:
                failed_copies += 1
                source, destination = file_info
                error_msg = f'Exception occurred: {exc}'
                results.append((False, source, destination, error_msg))
                log('Copy', f'EXCEPTION: {error_msg} - {source} -> {destination}', 'error',
                    logfile=logfile, logpath=log_path)
                
                # Update progress bar for exceptions
                progress_bar.set_postfix({
                    'Success': successful_copies, 
                    'Failed': failed_copies,
                    'Current': f"✗ {basename(source)} (ERROR)"
                })
                progress_bar.update(1)
        
        # Close progress bar
        progress_bar.close()
    
    # Log summary
    total_files = len(files)
    log('Copy', f'Parallel copy completed. Total: {total_files}, Success: {successful_copies}, Failed: {failed_copies}',
        logfile=logfile, logpath=log_path)
    
    return results

def update_copy_report(results, config):
    """
    Update the copy results report with new entries, avoiding duplicates.
    
    Args:
        results: List of tuples (success, source, destination, message) from file operations
        config: Configuration dictionary containing project paths
    
    Returns:
        int: Number of new entries added to the report
    """
    local_dir = config['Raw']
    project_root = dirname(local_dir)
    log_path = join(project_root, 'log')
    report_file = f'{log_path}/copy_results.json'
    
    # Load existing report if it exists
    existing_report = []
    if exists(report_file):
        try:
            with open(report_file, 'r') as f:
                existing_report = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing_report = []
    
    # Create a set of existing entries for duplicate detection
    # Use (source, destination) as unique identifier
    existing_entries = set()
    for entry in existing_report:
        if isinstance(entry.get('New file(s)'), list):
            # Handle multiple destination files (split files)
            for dest in entry['New file(s)']:
                existing_entries.add((entry['Original File'], dest))
        else:
            # Handle single destination file
            existing_entries.add((entry['Original File'], entry.get('New file(s)', '')))
    
    # Process new results and add only non-duplicates
    new_entries = []
    for res in results:
        source_file = res[1]
        dest_files = res[2]
        
        # Handle both single files and lists of files (for split .fif files)
        if isinstance(dest_files, list):
            # For split files, check each destination file
            for dest_file in dest_files:
                if (source_file, dest_file) not in existing_entries:
                    new_entries.append({
                        'Original File': source_file,
                        'Copy Date': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%y%m%d'),
                        'Copy Time': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%H%M%S'),
                        'New file(s)': dest_file,
                        'Transfer status': 'Success' if res[0] else 'Failed',
                        'message': res[3],
                        'timestamp': datetime.now().isoformat()
                    })
        else:
            # For single files
            if (source_file, dest_files) not in existing_entries:
                new_entries.append({
                    'Original File': source_file,
                    'Copy Date': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%y%m%d'),
                    'Copy Time': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%H%M%S'),
                    'New file(s)': dest_files,
                    'Transfer status': 'Success' if res[0] else 'Failed',
                    'message': res[3],
                    'timestamp': datetime.now().isoformat()
                })
    
    # Combine existing and new entries
    updated_report = existing_report + new_entries
    
    # Write updated report back to file
    with open(report_file, 'w') as f:
        json.dump(updated_report, f, indent=4)
    
    # Log summary of this session
    log('Copy', f'Report updated: {len(new_entries)} new entries added to existing {len(existing_report)} entries',
        logfile=config.get('Logfile', 'pipeline_log.log'), logpath=log_path)
    
    return len(new_entries)
    

def args_parser():
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

# Create local directories for each project
def main(config: Union[str, dict]=None):
    if config is None:
        args = args_parser()
        config_file = args.config
        if not config_file or not exists(config_file):
            config_file = askForConfig()
        if config_file:
            config = get_parameters(config_file)
            print(f'Using configuration file: {config_file}')
            
        else:
            print('No configuration file provided. Please provide a valid configuration file with -c or --config option.')
            return
    elif isinstance(config, str):
        # If config is a string, treat it as a file path
        config_file = config
        if exists(config_file):
            config = get_parameters(config_file)
            print(f'Using configuration file: {config_file}')
        else:
            print(f'Configuration file not found: {config_file}')
            return

    # If config is already a dict, use it as-is
    copy_squid_databases(config)
    
    # Perform parallel file copying
    results = parallel_copy_files(config, max_workers=8)
    
    # Update the copy report with new results
    new_entries_count = update_copy_report(results, config)
    
    print(f"Copy operation completed. {new_entries_count} new entries added to report.")

    return True

if __name__ == "__main__":
    main()
            