from glob import glob
import mne
import re
import json
import os
from shutil import copy2, copytree
import subprocess
from datetime import datetime
import filecmp
import time
import pandas as pd

sinuhe_root = 'neuro/data/sinuhe'
kaptah_root = 'neuro/data/kaptah'
local_root = 'neuro/data/local'

from utils import (
    log,
    headpos_patterns,
    proc_patterns,
    file_contains
)

global local_dir

with open('projects_to_sync.json', 'r') as f:
        # Load the list of projects to sync from the JSON file
        projects_to_sync = json.load(f)


timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = f'{timestamp}_copy.log'


def copy_if_newer_or_larger(source, destination):
    """
    Copy file from source to destination if source is newer or larger than destination.
    """
    if not os.path.exists(destination):
        copy2(source, destination)
    elif (os.path.getmtime(source) > os.path.getmtime(destination) or
        os.path.getsize(source) > os.path.getsize(destination)):
        copy2(source, destination)

def check_fif(source, destination):

    info_src = mne.io.read_info(source, verbose='error')
    info_dst = mne.io.read_info(destination, verbose='error')

    # for key in info_src:
    #     print(f'{key}: {info_src[key]}')
    # for key in info_dst:
    #     print(f'{key}: {info_dst[key]}')
    
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
        return True

    else:
        print(f'The following checks failed: {not_compare}')
        return False

def check_size_fif(source):
    raw_src = mne.io.read_raw(source, allow_maxshield=True, verbose='error')
    raw_size = raw_src._size
    print(f'{os.path.basename(source)}: {raw_size / 10000} GB')
    if raw_size > 20000:
        return True
    else:
        return False

def is_binary(file_path):
    """Check if a file is binary by reading a chunk of it."""
    with open(file_path, 'rb') as f:
        chunk = f.read(1024)  # Read first 1KB
        return b'\0' in chunk  # Binary files typically contain null bytes

def copy_from_sinuhe(project, check_existing=False):
    
    if not f"{projects_to_sync[project]['sinuhe']}":
        print('No TRIUX directory defined')
        pass
    
    else:
        # Create the local directory if it doesn't exist
        local_dir = f'{local_root}/{project}/raw'
        if not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)

        log_path = f'{local_root}/{project}/log'

        sinuhe = f"{sinuhe_root}/{projects_to_sync[project]['sinuhe']}"
        subjects  = glob(f'NatMEG_*', root_dir=sinuhe)
        subjects = sorted(list(set([s.split('_')[-1] for s in subjects])))
        
        non_dirs = [f for f in glob(f'*', root_dir=sinuhe) if not os.path.isdir(f'{sinuhe}/{f}')]
        
        for non_dir in non_dirs:
            source = f'{sinuhe}/{non_dir}'
            destination = f'{local_dir}/{non_dir}'
            if os.path.exists(destination):
                check = filecmp.cmp(source, destination, shallow=True)
                if check:
                    continue
                else:
                    copy_if_newer_or_larger(source, destination)
            else:
                copy_if_newer_or_larger(source, destination)
        for subject in subjects:
            sessions = sorted([ session for session in glob('*', root_dir = f'{sinuhe}/NatMEG_{subject}')
            if os.path.isdir(f'{sinuhe}/NatMEG_{subject}/{session}') and re.match(r'^\d{6}$', session)
            ])
            sinuhe_subject_dir = f'{sinuhe}/NatMEG_{subject}'
            if not os.path.exists(sinuhe_subject_dir):
                os.makedirs(sinuhe_subject_dir, exist_ok=True)
            
            non_dirs = [f for f in glob(f'*', root_dir=sinuhe_subject_dir) if not os.path.isdir(f'{sinuhe_subject_dir}/{f}')]
            
            local_subject_dir = f'{local_dir}/sub-{subject}'
            if not os.path.exists(local_subject_dir):
                os.makedirs(local_subject_dir, exist_ok=True)
        
            for non_dir in non_dirs:
                source = f'{sinuhe_subject_dir}/{non_dir}'
                destination = f'{local_subject_dir}/{non_dir}'
                if os.path.exists(destination):
                    check = filecmp.cmp(source, destination, shallow=True)
                    if check:
                        continue
                    else:
                        copy_if_newer_or_larger(source, destination)
                else:
                    copy_if_newer_or_larger(source, destination)
            
            for session in sessions:

                triux_src_path = f'{sinuhe}/NatMEG_{subject}/{session}/meg'
                triux_files = glob('*', root_dir=triux_src_path)
                triux_fif = [f for f in triux_files if re.search(r'\.fif$|\.fif\.gz$', f)]
                    # Other files are copied as they are
                triux_other = [f for f in triux_files if f not in triux_fif]
                triux_dst_path = f'{local_dir}/sub-{subject}/{session}/triux'
                if not os.path.exists(triux_dst_path):
                    os.makedirs(triux_dst_path, exist_ok=True)
                
                triux_compare = filecmp.dircmp(triux_src_path, triux_dst_path, ignore=['.DS_Store'])
                new_triux_files = triux_compare.left_only

                # First copy files that dont exist:
                for file in new_triux_files:
                    source = f'{sinuhe}/NatMEG_{subject}/{session}/meg/{file}'
                    destination = f'{triux_dst_path}/{file}'
                    print(f'Trying {source} --> {destination}')

                    if '.fif' in file and not file_contains(file, headpos_patterns + ['ave.fif']) and check_size_fif:
                        # Check if split
                        if not file_contains(file, [r'-\d+.fif'] + [r'-\d+_' + p for p in proc_patterns]):
                            try:
                                raw = mne.io.read_raw_fif(source, allow_maxshield=True, verbose='error')
                                raw.save(destination, overwrite=True, verbose='error')
                                log(f'Copied (split if > 2GB) {source} --> {destination}', logfile=log_file, logpath=log_path)
                            except Exception as e:
                                log(f'{source} !!! {destination} {e}', 'error',logfile=log_file, logpath=log_path)
                            continue
                    else:
                        copy_if_newer_or_larger(source, destination)
                        log(f'Copied {source} --> {destination}', logfile=log_file, logpath=log_path)

                # Check files that exist in both source and destination
                if check_existing:
                    for file in triux_files:
                        source = f'{sinuhe}/NatMEG_{subject}/{session}/meg/{file}'
                        destination = f'{triux_dst_path}/{file}'
                        print(f'Checking if {source} == {destination}')
                        check = filecmp.cmp(source, destination, shallow=True)
                        if check:
                            print('Nothing to update')
                            continue
                        else:
                            copy_if_newer_or_larger(source, destination)
                            log(f'Updated {source} --> {destination}', logfile=log_file, logpath=log_path)

def copy_from_kaptah(project, check_existing=False):

    if not f"{projects_to_sync[project]['kaptah']}":
        print('No Hedscan directory defined')
        pass

    else:

        # Create the local directory if it doesn't exist
        local_dir = f'{local_root}/{project}/raw'
        if not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        log_path = f'{local_root}/{project}/log'

        kaptah = f"{kaptah_root}/{projects_to_sync[project]['kaptah']}"
        subjects  = glob(f'sub-*', root_dir=kaptah)
        subjects = sorted(list(set([s.split('-')[-1] for s in subjects])))
        
        non_dirs = [f for f in glob(f'*', root_dir=kaptah) if not os.path.isdir(f'{kaptah}/{f}')]
        
        for non_dir in non_dirs:
            source = f'{kaptah}/{non_dir}'
            destination = f'{local_dir}/{non_dir}'
            if os.path.exists(destination):
                check = filecmp.cmp(source, destination, shallow=True)
                if check:
                    continue
                else:
                    copy_if_newer_or_larger(source, destination)
            else:
                copy_if_newer_or_larger(source, destination)
        
        for subject in subjects:

            all_files = glob(f'*', root_dir=f'{kaptah}/sub-{subject}')
            # Extract unique dates from session folder names (assuming date format in session name, e.g., '20240607')
            hedscan_dates = set()
            for session in all_files:
                match = re.search(r'(\d{8})', session)
                if match:
                    hedscan_dates.add(match.group(1)[2:])
            sessions = sorted(list(hedscan_dates))

            for session in sessions:

                hedscan_src_path = f'{kaptah}/sub-{subject}'
                hedscan_files = glob(f'20{session}*', root_dir = hedscan_src_path)
                hedscan_dst_path = f'{local_dir}/sub-{subject}/{session}/hedscan'
                if not os.path.exists(hedscan_dst_path):
                    os.makedirs(hedscan_dst_path, exist_ok=True)

                files_in_dst = glob('*', root_dir=hedscan_dst_path)

                
                source_files_renamed = [f.split('file-') for f in hedscan_files]
                
                df = pd.DataFrame(source_files_renamed)

                df['run'] = df.groupby(1).cumcount() + 1
                
                df['old_name'] = df[0] + 'file-' + df[1]
                df[['pre', 'post']] = df[1].str.rsplit('_', n=1, expand=True)
                
                df['new_name'] = df.apply(
                    lambda row: row['pre'] + '_' + ('dup' + str(row['run']) + '_' if row['run'] != 1 else '') + row['post'], axis=1)

                df['in_dst'] = df.apply(
                    lambda row: row['new_name'] in files_in_dst, axis=1
                )

                new_hedscan_files = df[df['in_dst'] == False]['old_name'].tolist()

                # First copy files that dont exist:
                for file in new_hedscan_files:
                    source = f'{kaptah}/sub-{subject}/{file}'
                    
                    new_file = df[df['old_name'] == file]['new_name'].values[0]

                    #new_file = f"{file.split('file-')[-1]}"
                    destination = f'{hedscan_dst_path}/{new_file}'
                    print(f'Trying {source} --> {destination}')

                    if '.fif' in file and not file_contains(file, headpos_patterns) and check_size_fif:
                        # Check if split
                        if not file_contains(file, [r'-\d+.fif']):
                            try:
                                raw = mne.io.read_raw_fif(source, allow_maxshield=True, verbose='error')
                                raw.save(destination, overwrite=True, verbose='error')
                                log(f'Copied (split if > 2GB) {source} --> {destination}', logfile=log_file, logpath=log_path)
                            except Exception as e:
                                log(f'{source} !!! {destination} {e}', 'error', logfile=log_file, logpath=log_path)
                        else:
                            continue
                    else:
                        copy_if_newer_or_larger(source, destination)
                        log(f'Copied {source} --> {destination}', logfile=log_file, logpath=log_path)
                
                # Check files that exist in both source and destination
                if check_existing:
                    for file in hedscan_files:
                        source = f'{kaptah}/sub-{subject}/{file}'
                        new_file = f"{file.split('file-')[-1]}"
                        destination = f'{hedscan_dst_path}/{new_file}'

                        print(f'Checkin {source} == {destination}')
                        if file.endswith('.fif') and not file_contains(file, headpos_patterns):
                            check = check_fif(source, destination)
                        else:
                            check = filecmp.cmp(source, destination, shallow=True)
                        if check:
                            print('Nothing to update')
                            continue
                        else:
                            copy_if_newer_or_larger(source, destination)
                            log(f'Updated {source} --> {destination}', logfile=log_file, logpath=log_path)           

def check_file_size(project, wait_time=30):
    previous_triux_sizes = {}
    previous_hedscan_sizes = {}
    size_triux_changed = False
    size_hedscan_changed = False

    if f"{projects_to_sync[project]['sinuhe']}":
        sinuhe_path = f"{sinuhe_root}/{projects_to_sync[project]['sinuhe']}"
        full_s_paths = [os.path.join(root, file) for root, dirs, files in 
                      os.walk(sinuhe_path, topdown=True) for file in files]
    if f"{projects_to_sync[project]['kaptah']}":
        kaptah_path = f"{kaptah_root}/{projects_to_sync[project]['kaptah']}"
        full_k_paths = [os.path.join(root, file) for root, dirs, files in 
                       os.walk(kaptah_path, topdown=True) for file in files]

    print(f'Checking for new files to sync in {project}...')
    time.sleep(wait_time)
    current_s_sizes = {full_path: os.path.getsize(full_path) for full_path in full_s_paths}
    current_k_sizes = {full_path: os.path.getsize(full_path) for full_path in full_k_paths}
    
    for file, size in current_s_sizes.items():
        if file in previous_triux_sizes:
            if size != previous_triux_sizes[file]:
                print(f'File size changed: {file} (New size: {size} bytes)')
                size_triux_changed = False
        previous_triux_sizes[file] = size
    
    for file, size in current_k_sizes.items():
        if file in previous_hedscan_sizes:
            if size != previous_hedscan_sizes[file]:
                print(f'File size changed: {file} (New size: {size} bytes)')
                size_hedscan_unchanged = False
        previous_hedscan_sizes[file] = size

    return size_triux_changed, size_hedscan_changed

# Create local directories for each project
def main():
    # Start monitoring file size changes in the local directory

    for project in projects_to_sync:

        #triux_changed, hedscan_changed = check_file_size(project, 15)

        print(f'TRIUX files changed for {project}, copying from Sinuhe...')
        copy_from_sinuhe(project, check_existing=False)
        print(f'Hedscan files changed for {project}, copying from Kaptah...')
        copy_from_kaptah(project, check_existing=False)

if __name__ == "__main__":
    main()
            