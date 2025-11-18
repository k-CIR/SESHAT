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
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import sys

calibration = '/neuro/databases/sss/sss_cal.dat'
crosstalk = '/neuro/databases/ctc/ct_sparse.fif'

from utils import (
    log, configure_logging,
    headpos_patterns,
    proc_patterns,
    file_contains,
    askForConfig,
    project_paths
)

global local_dir

def check_fif(file_path):
    """Check if a file is a .fif file based on its extension."""
    is_fif = file_contains(basename(file_path), [r'\.fif$', r'\.fif'])
    is_large = getsize(file_path) > _get_split_size('2GB')
    is_fif_spec = file_contains(basename(file_path), headpos_patterns + ['ave.fif', 'config.fif'])
    is_split = file_contains(basename(file_path), [r'-\d+.fif'] + [r'-\d+_' + p for p in proc_patterns])
    fif_check = {
        'is_fif': is_fif,
        'is_large': is_large,
        'is_fif_spec': is_fif_spec,
        'is_split': is_split
    }
    return fif_check

def get_split_file_parts(file_path):
    """
    Get all parts of a potentially split .fif file following MNE naming convention.
    
    Args:
        base_file: Base .fif file path
        
    Returns:
        list: All file parts that exist (base file and any split parts)
    """
    if not exists(file_path):
        return file_path
    
    parts = [file_path]
    base_path = re.sub(r'-\d+\.fif$', '.fif', file_path).replace('.fif', '')
    
    # Look for split files: filename_raw-1.fif, filename_raw-2.fif, etc.
    i = 1
    while True:
        split_file = f"{base_path}-{i}.fif"
        if exists(split_file):
            parts.append(split_file)
            i += 1
        else:
            break
    
    if len(parts) == 1:
        return file_path
    else:
        return parts

def check_match(source, destination, size_tolerance_bytes=4096, check_info=False):
    """
    Check if the file has been transferred correctly by comparing source and destination.
    For .fif files, use MNE to read and compare metadata.
    For other files, use filecmp.
    """
    match = False
    info_match = True

    if isinstance(destination, list):
        destination = destination[0]
    
    if not exists(destination):
        match = False
    
    else:
        # Make a simple directory comparison if both are directories
        if isdir(source):
            match = filecmp.dircmp(source, destination).funny_files == []
        
        # Get source size for all file types
        source_size = getsize(source)
        
        # Check if fif file
        if check_fif(source)['is_fif']:
            
            # Check metadata if requested, might take longer time
            
            if check_info:
                info_src = read_info(source, verbose='error')
                info_dst = read_info(destination, verbose='error')

                metadata_checks = {
                'meas_id_version': info_src['meas_id']['version'] == info_dst['meas_id']['version'],
                'secs': info_src['meas_id']['secs'] == info_dst['meas_id']['secs'],
                'date': info_src['meas_date'] == info_dst['meas_date'],
                'sfreq': info_src['sfreq'] == info_dst['sfreq'],
                'nchan': info_src['nchan'] == info_dst['nchan']
                }
                info_match = all(metadata_checks.values())
            
            # Just check fif-size (sum split files if any)
            if isinstance(get_split_file_parts(destination), list):
                dest_size = sum([getsize(dest) for dest in get_split_file_parts(destination)])
            else:
                dest_size = getsize(destination)
        else:
            # For non-fif files, simple size comparison
            dest_size = getsize(destination)
        
        # Calculate tolerance - for large files (>100MB), use 0.1% or min 4KB
        if source_size > 100 * 1024 * 1024:  # 100MB
            tolerance = max(size_tolerance_bytes, int(source_size * 0.001))  # 0.1%
        else:
            tolerance = size_tolerance_bytes
        
        size_diff = abs(source_size - dest_size)
        
        match_size = size_diff <= tolerance
        
        destination_newer = getmtime(source) < getmtime(destination) + 10 # within 10 seconds
        
        match = all([match_size, destination_newer, info_match])
    
    return match, source, destination

def copy_file_or_dir(source, destination):
    """
    Copy file from source to destination.
    """
    if isdir(source):
        copytree(source, destination)
    else:
        copy2(source, destination)

def copy_squid_databases(calibration_path=None, crosstalk_path=None):
    
    calibration_dest = calibration_path
    crosstalk_dest = crosstalk_path
    
    if calibration and exists(calibration):
        if not exists(dirname(calibration_dest)):
            os.makedirs(dirname(calibration_dest), exist_ok=True)    
        copy_data(calibration, calibration_dest)
    else:
        print(f'Calibration file {calibration} does not exist.')
    
    if crosstalk and exists(crosstalk):
        if not exists(dirname(crosstalk_dest)):
            os.makedirs(dirname(crosstalk_dest), exist_ok=True)
        copy_data(crosstalk, crosstalk_dest)
    else:
        print(f'Crosstalk file {crosstalk} does not exist.')

def copy_data(source, destination):
    """
    Copy file from source to destination with intelligent handling of .fif files.
    
    Args:
        source: Source file path
        destination: Destination file path
        logfile: Optional log filename
        log_path: Optional log directory path
    """
    existing_file = 0
    new_file = 0
    failed_file = 0

    if check_match(source, destination)[0]:
        
       match = True
       source = get_split_file_parts(source)
       destination = get_split_file_parts(destination)
       message = "Copied"
       level = 'info'
       existing_file = 1

    if not check_match(source, destination)[0]:

        os.makedirs(dirname(destination), exist_ok=True)
        
        # Files are different, need to handle based on file type
        is_fif, fif_large, fif_special, is_split = check_fif(source).values()
        use_mne_read_raw = all([is_fif, fif_large, not fif_special, not is_split])
        
        if use_mne_read_raw:
            # Check if larger than 2GB
            try:
                raw = read_raw(source, allow_maxshield=True, verbose='error')
                raw.save(destination, overwrite=True, verbose='error')
                # Use fast method to get split file parts (avoids slow read_raw)
                destination = get_split_file_parts(destination)
                message = f'Copied (split if > 2GB)'
                match = True
                level = 'info'
                new_file = 1

            except Exception as e:
                try:
                    copy_file_or_dir(source, destination)
                    match = True
                    message = f'Fail (MNE failed)'
                    level = 'warning'
                    new_file = 1
                except Exception as e2:
                    match = False
                    message = f'Fail {str(e2)}'
                    level = 'error'
                    failed_file = 1
        else:
            # For non-fif files, use standard copy logic
            copy_file_or_dir(source, destination)
            match = True
            message = f'Copied'
            level = 'info'
            new_file = 1
    
    return match, source, destination, message, existing_file, new_file, failed_file

def make_process_list(paths, check_existing=False):
    
    local_dir = paths['raw']
    if not exists(local_dir):
        os.makedirs(local_dir, exist_ok=True)
            
    project_root = paths['project_root']
    log_path = paths['logs']
    logfile = paths['log_file']
    docspath = paths.get('docs', '')
    scriptspath = paths.get('scripts', '')
    
    sinuhe = paths.get('sinuhe', '')
    kaptah = paths.get('kaptah', '')
    
    files = []
    
    if sinuhe:
        natmeg_subjects  = [s for s in glob(f'NatMEG_*', root_dir=sinuhe) if isdir(f'{sinuhe}/{s}')]
        subjects = sorted(list(set([s.split('_')[-1] for s in natmeg_subjects])))
        other_files_and_dirs = [f for f in glob(f'*', root_dir=sinuhe) if f not in natmeg_subjects]

        for item in other_files_and_dirs:
            source = f'{sinuhe}/{item}'
            destination = f'{docspath}/{item}'
            files.append(check_match(source, destination))

            # copy_file(source, destination, logfile=logfile, log_path=log_path)
        
        for subject in subjects:
            sessions = sorted([session for session in glob('*', root_dir = f'{sinuhe}/NatMEG_{subject}')
            if isdir(f'{sinuhe}/NatMEG_{subject}/{session}') and re.match(r'^\d{6}$', session)
            ])
            sinuhe_subject_dir = f'{sinuhe}/NatMEG_{subject}'
            local_subject_docs_dir = f'{docspath}/sub-{subject}'
            local_subject_dir = f'{local_dir}/sub-{subject}'
            
            items = [f for f in glob(f'*', root_dir=sinuhe_subject_dir) if f not in sessions]
            for item in items:
                source = f'{sinuhe_subject_dir}/{item}'
                destination = f'{local_subject_docs_dir}_{item}'
                files.append(check_match(source, destination))

                # copy_file(source, destination, logfile=logfile, log_path=log_path)
                
            for session in sessions:
                items = [f for f in glob(f'*', root_dir=f'{sinuhe_subject_dir}/{session}/meg')]
                for item in items:
                    source = f'{sinuhe_subject_dir}/{session}/meg/{item}'
                    destination = f'{local_dir}/sub-{subject}/{session}/triux/{item}'
                    files.append(check_match(source, destination))
                    # copy_file(source, destination, logfile=logfile, log_path=log_path)
    elif not isdir(sinuhe):
            log('Copy', f"{sinuhe} is not a directory", 'error', logfile)
    
    elif not glob('*', root_dir=sinuhe):
        log('Copy', f"{sinuhe} is empty", 'warning', logfile)
    else: 
        log('Copy', 'No TRIUX directory defined', 'warning', logfile)

    
    if kaptah:
        kaptah_subjects  = [s for s in glob(f'sub-*', root_dir=kaptah) if isdir(f'{kaptah}/{s}')]
        
        other_files_and_dirs = [f for f in glob(f'*', root_dir=kaptah) if f not in kaptah_subjects]
        
        subjects = sorted(list(set([s.split('-')[-1] for s in kaptah_subjects])))
        
        for item in other_files_and_dirs:
            source = f'{kaptah}/{item}'
            destination = f'{docspath}/{item}'
            files.append(check_match(source, destination))
        
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
                destination = f'{docspath}/sub-{subject}_{item}'
                files.append(check_match(source, destination))

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
                    
                    files.append(check_match(source, destination))
    
    elif not isdir(kaptah):
            log('Copy', f"{kaptah} is not a directory", 'error', logfile)
    
    elif not glob('*', root_dir=kaptah):
        log('Copy', f"{kaptah} is empty", 'warning', logfile)
    else: 
        log('Copy', 'No Hedscan directory defined', 'warning', logfile)

    return files

def process_file_worker(file_info, logfile):
    """
    Worker function to process a single file transfer.
    
    Args:
        file_info: Tuple of (source, destination)
        logfile: Log filename
        log_path: Log directory path
    
    Returns:
        Tuple of (success, source, destination, message)
    """
    match, source, destination = file_info

    try:
        match, source, destination, msg, existing_file, new_file, failed_file = copy_data(source, destination)
    except Exception as e:
        msg = f"Error processing file: {str(e)}"
        match = False
        failed_file = 1

    return match, source, destination, msg, existing_file, new_file, failed_file

def parallel_copy_files(paths, max_workers=4):
    """
    Copy files in parallel using ThreadPoolExecutor.
    
    Args:
        paths: directories
        max_workers: Maximum number of worker threads
    
    Returns:
        List of results from file processing
    """
    files = make_process_list(paths)
    files_to_process = [file for file in files if not file[0]]
    
    # Extract log configuration from config
    
    
    local_dir = paths.get('raw', '')
    project_root = paths.get('project_root', '')
    logfile = paths.get('log_file', '')

    results = []
    new_file_count = 0
    existing_file_count = len([file for file in files if file[0]])
    failed_file_count = 0
    
    pbar = tqdm(total=len(files_to_process), 
                       desc="Copy files", 
                       unit=f' file(s)',
                       disable=not sys.stdout.isatty(),
                       ncols=80,
                       bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')

    # Use ThreadPoolExecutor for I/O bound operations like file copying
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_file_worker, file_info, logfile): file_info 
            for file_info in files
        }
        
        # Process completed tasks
        for future in as_completed(future_to_file):
            file_info = future_to_file[future]
            
            try:
                match, source, destination, message, existing_file, new_file, failed_file = future.result()
                results.append((match, source, destination, message))
                
                failed_file_count += failed_file
                new_file_count += new_file
                # Update progress bar
                status = "✓" if match else "✗"
                pbar.set_postfix({
                    'New files': new_file_count,
                    'Existing files': existing_file_count,
                    'Failed': failed_file_count,
                    'Latest': f"{status} {basename(source)}"
                })
                pbar.update(1)
                    
            except Exception as exc:
                failed_file_count += 1
                match, source, destination = file_info
                error_msg = f'Exception occurred: {exc}'
                results.append((False, source, destination, error_msg))
                log('Copy', f'EXCEPTION: {error_msg} - {source} -> {destination}', 'error', logfile)
                
                # Update progress bar for exceptions
                pbar.set_postfix({
                    'New files': new_file_count,
                    'Existing files': existing_file_count,
                    'Failed': failed_file_count,
                    'Latest': f"✗ {basename(source)} (ERROR)"
                })
                pbar.update(1)
            
            print(f'{new_file_count}/{len(files_to_process)}')
        # Close progress bar
        pbar.close()
    # Log summary
    log('Copy', f'Parallel copy completed. Files to process: {len(files_to_process)}, Success: {new_file_count}, Failed: {failed_file_count}',
        'info',
        logfile)

    return results

def update_copy_report(results, paths):
    """
    Update the copy results report with new entries, avoiding duplicates.
    
    Args:
        results: List of tuples (success, source, destination, message) from file operations
        paths: Project paths
    
    Returns:
        int: Number of new entries added to the report
    """
    
    logfile = paths['log_file']
    report_file = f'{paths['logs']}/copy_results.json'
    
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
    # Group results by source file to handle multiple destinations correctly
    source_groups = {}
    for res in results:
        source_file = res[1]
        dest_files = res[2]
        
        if source_file not in source_groups:
            source_groups[source_file] = {
                'success': res[0],
                'message': res[3],
                'destinations': dest_files
            }
    
    new_entries = []
    for source_file, group_info in source_groups.items():
        # Filter out destinations that already exist in the report
        new_destinations = []
        
        if isinstance(group_info['destinations'], list):
            for dest_file in group_info['destinations']:
                if (source_file, dest_file) not in existing_entries:
                    new_destinations.append(dest_file)
        else:
            if (source_file, group_info['destinations']) not in existing_entries:
                new_destinations = group_info['destinations']
        
        # Only create an entry if there are new destinations
        if new_destinations:
            # Get file sizes
            original_size = None
            if exists(source_file):
                try:
                    original_size = getsize(source_file)
                except (OSError, FileNotFoundError):
                    original_size = None
            
            # Calculate destination file sizes
            dest_size = None
            try:
                if isinstance(new_destinations, list):
                    dest_size = sum([getsize(dest) for dest in new_destinations if exists(dest)])
                else:
                    dest_size = getsize(new_destinations) if exists(new_destinations) else None
            except (OSError, FileNotFoundError):
                dest_size = None

            # Prepare size values (single value or list matching destination structure)

            new_entries.append({
                'Original File': source_file,
                'Copy Date': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%y%m%d'),
                'Copy Time': datetime.fromtimestamp(os.path.getctime(source_file)).strftime('%H%M%S'),
                'New file(s)': new_destinations,
                'Original Size': original_size,
                'Total Destination Size': dest_size,
                'Transfer Status': 'Success' if group_info['success'] else 'Failed',
                'status': group_info['message'],  # Standardized field name for filtering
                'timestamp': datetime.now().isoformat()
            })
    
    # Combine existing and new entries
    updated_report = existing_report + new_entries
    
    # Write updated report back to file
    with open(report_file, 'w') as f:
        json.dump(updated_report, f, indent=4)
    
    # Log summary of this session
    log('Copy', f'Report updated: {len(new_entries)} new entries added to existing {len(existing_report)} entries',
        'info',
        logfile)
    
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
def main(config: str=None):

    if config is None:
        args = args_parser()
        config = args.config
        if not config or not exists(config):
            config = askForConfig()

    paths = project_paths(config, init=True)
    # If config is already a dict, use it as-is
    copy_squid_databases(paths['Calibration'], paths['Crosstalk'])
    
    # Perform parallel file copying
    results = parallel_copy_files(paths, max_workers=8)
    update_copy_report(results, paths)
    return True

if __name__ == "__main__":
    main()
            