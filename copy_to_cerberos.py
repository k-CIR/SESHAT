from glob import glob
from mne.io import read_raw, read_info
from mne._fiff.write import _get_split_size
from mne.viz.utils import compare_fiff
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
import hashlib

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
    Copy file from source to destination if source is newer, larger, or different.
    Uses more sophisticated comparison for better reliability.
    """
    if not exists(destination):
        if isdir(source):
            copytree(source, destination)
        else:
            copy2(source, destination)
    else:
        should_copy = False
        
        # Check if source is newer
        if getmtime(source) > getmtime(destination):
            should_copy = True
        
        # Check size difference - but be tolerant of small differences
        src_size = getsize(source)
        dst_size = getsize(destination)
        size_diff_percent = abs(src_size - dst_size) / max(src_size, 1) * 100
        
        # If size difference is significant (>1%), copy
        if size_diff_percent > 1:
            should_copy = True
        # For small size differences, use checksum to decide
        elif size_diff_percent > 0:
            src_checksum = calculate_file_checksum(source)
            dst_checksum = calculate_file_checksum(destination)
            if src_checksum and dst_checksum and src_checksum != dst_checksum:
                should_copy = True
        
        if should_copy:
            if isdir(source):
                copytree(source, destination, dirs_exist_ok=True)
            else:
                copy2(source, destination)

def check_fif(source, destination):

    fnames_src = read_raw(source, allow_maxshield=True, verbose='error').filenames
    info_src = read_info(source, verbose='error')
    [print(k, v) for k, v in info_src.items()]
    fnames_dst = read_raw(destination, allow_maxshield=True, verbose='error').filenames
    info_dst = read_info(destination, verbose='error')

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
        return True, [str(f) for f in fnames_src][0], [str(f) for f in fnames_dst]

    else:
        print(f'The following checks failed: {not_compare}')
        return False, [str(f) for f in fnames_src][0], [str(f) for f in fnames_dst]

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

def calculate_file_checksum(file_path, algorithm='sha256', chunk_size=8192):
    """Calculate checksum for a file to verify integrity."""
    hash_algo = hashlib.new(algorithm)
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hash_algo.update(chunk)
        return hash_algo.hexdigest()
    except Exception as e:
        print(f"Error calculating checksum for {file_path}: {e}")
        return None

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
    For other files, use checksums for reliable comparison.
    """
    match = False
    if not exists(destination):
        match = False
    else:
        if isdir(source):
            match = filecmp.dircmp(source, destination).funny_files == []
        # Check if fif file and size > 2GB, then expecting split and use check_fif
        elif all([file_contains(basename(source), [r'\.fif$', r'\.fif']), check_size_fif(source)]):
            match, source, destination = check_fif(source, destination)
        else:
            # For regular files, first try quick size comparison
            src_size = getsize(source)
            dst_size = getsize(destination)
            
            # If sizes are very different (>1% difference), files are definitely different
            size_diff_percent = abs(src_size - dst_size) / max(src_size, 1) * 100
            if size_diff_percent > 1:
                match = False
            else:
                # For small size differences or equal sizes, use checksum comparison
                src_checksum = calculate_file_checksum(source)
                dst_checksum = calculate_file_checksum(destination)
                
                if src_checksum and dst_checksum:
                    match = src_checksum == dst_checksum
                else:
                    # Fallback to byte-by-byte comparison if checksum fails
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
                return True, source, destination
            except Exception as e:
                try:
                    copy_if_newer_or_larger(source, destination)
                    if logfile and log_path:
                        log('Copy', f'Fallback copy: {source} --> {destination} (MNE failed: {e})', 'warning',
                            logfile=logfile, logpath=log_path)
                    return True, source, destination
                except Exception as e2:
                    if logfile and log_path:
                        log('Copy', f'Copy failed: {source} --> {destination} ({e2})', 'error',
                            logfile=logfile, logpath=log_path)
                    return False, source, destination
        else:
            # For non-fif files, use standard copy logic
            try:
                copy_if_newer_or_larger(source, destination)
                if logfile and log_path:
                    log('Copy', f'{source} --> {destination}', 'info',
                            logfile=logfile, logpath=log_path)
                return True, source, destination
            except Exception as e:
                if logfile and log_path:
                    log('Copy', f'Copy failed: {source} --> {destination} ({e})', 'error',
                        logfile=logfile, logpath=log_path)
                return False, source, destination

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
                                if f.startswith(f'20{session}')])

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
            if success:
                msg = "Copy completed successfully"
                operation_success = True
            else:
                msg = "Copy failed"
                operation_success = False
        else:
            msg = "File already up to date"
            operation_success = True  # File is already correct, consider this success
    except Exception as e:
        msg = f"Error processing file: {str(e)}"
        operation_success = False

    return operation_success, source, destination, msg

def parallel_copy_files(config, max_workers=16):
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
    Update the copy results report with new entries, consolidating by original file.
    Each original file appears once with multiple destinations as lists when applicable.
    
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
    
    # Convert existing report to consolidated format (group by original file)
    consolidated_report = {}
    for entry in existing_report:
        original_file = entry['Original File']
        new_files = entry.get('New file(s)', '')
        
        if original_file not in consolidated_report:
            # Create new consolidated entry
            consolidated_report[original_file] = {
                'Original File': original_file,
                'Copy Date': entry.get('Copy Date', ''),
                'Copy Time': entry.get('Copy Time', ''),
                'New file(s)': [],
                'Transfer status': entry.get('Transfer status', 'Unknown'),
                'message': entry.get('message', ''),
                'timestamp': entry.get('timestamp', '')
            }
        
        # Add destination files to the list
        if isinstance(new_files, list):
            consolidated_report[original_file]['New file(s)'].extend(new_files)
        elif new_files:  # Single file, not empty
            consolidated_report[original_file]['New file(s)'].append(new_files)
    
    # Process new results and consolidate by original file
    new_consolidated = {}
    for res in results:
        source_file = res[1]
        dest_files = res[2]
        success = res[0]
        message = res[3]
        
        if source_file not in new_consolidated:
            # Create new consolidated entry for this source file
            new_consolidated[source_file] = {
                'Original File': source_file,
                'Copy Date': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%y%m%d'),
                'Copy Time': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%H%M%S'),
                'New file(s)': [],
                'Transfer status': 'Success' if success else 'Failed',
                'message': message,
                'timestamp': datetime.now().isoformat()
            }
        
        # Add destination files to the consolidated entry
        if isinstance(dest_files, list):
            new_consolidated[source_file]['New file(s)'].extend(dest_files)
        else:
            new_consolidated[source_file]['New file(s)'].append(dest_files)
        
        # Update status - if any operation failed, mark as failed
        if not success:
            new_consolidated[source_file]['Transfer status'] = 'Failed'
    
    # Merge new consolidated entries with existing ones
    for source_file, new_entry in new_consolidated.items():
        if source_file in consolidated_report:
            # Merge with existing entry - add new destinations
            existing_entry = consolidated_report[source_file]
            existing_dests = set(existing_entry['New file(s)'])
            new_dests = set(new_entry['New file(s)'])
            
            # Only add truly new destinations
            unique_new_dests = new_dests - existing_dests
            if unique_new_dests:
                existing_entry['New file(s)'].extend(list(unique_new_dests))
                existing_entry['timestamp'] = new_entry['timestamp']
                # Update status if this operation failed
                if new_entry['Transfer status'] == 'Failed':
                    existing_entry['Transfer status'] = 'Failed'
        else:
            # Add completely new entry
            consolidated_report[source_file] = new_entry
    
    # Convert consolidated format back to list, ensuring 'New file(s)' is properly formatted
    final_report = []
    for entry in consolidated_report.values():
        # If only one destination file, keep as string for consistency
        if len(entry['New file(s)']) == 1:
            entry['New file(s)'] = entry['New file(s)'][0]
        # If multiple files, keep as list
        final_report.append(entry)
    
    # Write consolidated report back to file
    with open(report_file, 'w') as f:
        json.dump(final_report, f, indent=4)
    
    # Count new entries added
    new_entries_count = len(new_consolidated)
    
    # Log summary of this session
    log('Copy', f'Report updated: {new_entries_count} new consolidated entries, total {len(final_report)} entries',
        logfile=config.get('Logfile', 'pipeline_log.log'), logpath=log_path)
    
    return new_entries_count
    

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
            