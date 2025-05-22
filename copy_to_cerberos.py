from glob import glob
import mne
import re
import json
import os
from shutil import copy2, copytree
import subprocess
from datetime import datetime
import filecmp

sinuhe_path = '/neuro/data/sinuhe'
kaptah_path = '/neuro/data/kaptah'
local_path = '/neuro/data/local'

from utils import (
    log,
    headpos_patterns,
    file_contains
)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
def copy_if_newer_or_larger(source, destination):
    """
    Copy file from source to destination if source is newer or larger than destination.
    """
    if not os.path.exists(destination):
        copy2(source, destination)
    elif (os.path.getmtime(source) > os.path.getmtime(destination) or
        os.path.getsize(source) > os.path.getsize(destination)):
        copy2(source, destination)

def is_binary(file_path):
    """Check if a file is binary by reading a chunk of it."""
    with open(file_path, 'rb') as f:
        chunk = f.read(1024)  # Read first 1KB
        return b'\0' in chunk  # Binary files typically contain null bytes

with open('projects_to_sync.json', 'r') as f:
    # Load the list of projects to sync from the JSON file
    projects_to_sync = json.load(f)
    
# Create local directories for each project
for project in projects_to_sync:
    
    log_file = f'{timestamp}_copy.log'
    log_path = f'{local_path}/{project}/log'
    
    # Create the local directory if it doesn't exist
    
    local_dir = f'{local_path}/{project}/raw'
    if not os.path.exists(local_dir):
        os.makedirs(local_dir, exist_ok=True)
    
    if f"{projects_to_sync[project]['sinuhe']}":
        sinuhe = f"{sinuhe_path}/{projects_to_sync[project]['sinuhe']}"
        triux_subjects  = glob(f'NatMEG_*', root_dir=sinuhe)
        triux_subjects = [s.split('_')[-1] for s in triux_subjects]
        
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
        
    else:
        triux_subjects = []
        
    if f"{projects_to_sync[project]['kaptah']}":
        kaptah = f"{kaptah_path}/{projects_to_sync[project]['kaptah']}"
        hedscan_subjects  = glob(f'sub-*', root_dir=kaptah)
        hedscan_subjects = [s.split('-')[-1] for s in hedscan_subjects]
        
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
        
    else:
        hedscan_subjects = []
    
    subjects = list(set(triux_subjects) & set(hedscan_subjects))

    for subject in subjects:
        # Get the list of all files in the project directory
        if sinuhe:
            triux_sessions = glob(f'*', root_dir=f'{sinuhe}/NatMEG_{subject}')
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

        else:
            triux_sessions = []
        if kaptah:
            hedscan_sessions = glob(f'*', root_dir=f'{kaptah}/sub-{subject}')
            # Extract unique dates from session folder names (assuming date format in session name, e.g., '20240607')
            hedscan_dates = set()
            for session in hedscan_sessions:
                match = re.search(r'(\d{8})', session)
                if match:
                    hedscan_dates.add(match.group(1)[2:])

        else:
            hedscan_dates = []
        
        sessions = list(set(triux_sessions) & hedscan_dates)
        
        for session in sessions:

            # Get the list of all files in the session directory
            if sinuhe:
                triux_src_path = f'{sinuhe}/NatMEG_{subject}/{session}/meg'
                triux_files = glob('*', root_dir=triux_src_path)
                triux_fif = [f for f in triux_files if re.search(r'\.fif$|\.fif\.gz$', f)]
                    # Other files are copied as they are
                triux_other = [f for f in triux_files if f not in triux_fif]
                triux_dst_path = f'{local_dir}/sub-{subject}/{session}/triux'
                if not os.path.exists(triux_dst_path):
                    os.makedirs(triux_dst_path, exist_ok=True)
                
                triux_compare = filecmp.dircmp(triux_src_path, triux_dst_path, ignore=['.DS_Store'])
                new_triux_files = [f"{f.split('file-')[-1]}" for f in triux_compare.left_only]
            else:
                triux_fif = []
                triux_other = []
                triux_dst_path = None

            if kaptah:
                hedscan_src_path = f'{kaptah}/sub-{subject}'
                hedscan_files = glob('*', root_dir = hedscan_src_path)
                hedscan_fif = [f for f in hedscan_files if re.search(r'\.fif$|\.fif\.gz$', f)]
                
                    # Other files are copied as they are
                hedscan_other = [f for f in hedscan_files if f not in hedscan_fif]
                hedscan_dst_path = f'{local_dir}/sub-{subject}/{session}/hedscan'
                if not os.path.exists(hedscan_dst_path):
                    os.makedirs(hedscan_dst_path, exist_ok=True)
                
                hedscan_compare = filecmp.dircmp(hedscan_src_path, hedscan_dst_path, ignore=['.DS_Store'])
                new_hedscan_files = [f"{f.split('file-')[-1]}" for f in hedscan_compare.left_only]
                # Check if files in new_hedscan_files already exist in the destination
                existing_files = set(glob('*', root_dir=hedscan_dst_path))
                new_hedscan_files = [f for f in new_hedscan_files if f not in existing_files]

            else:
                hedscan_fif = []
                hedscan_other = []
            
            # Destination directory for the subject and session
            if new_triux_files:
                for file in triux_files:
                    # Copy the file to the local directory
                        
                    source = f'{sinuhe}/NatMEG_{subject}/{session}/meg/{file}'
                    destination = f'{triux_dst_path}/{file}'
                    
                    if os.path.isdir(source):
                        copytree(source, destination, dirs_exist_ok=True)
                        continue

                    if file.endswith('.fif') and not file_contains(file, headpos_patterns):
                        
                        # If the file is a .fif file, use mne to read and write it
                        # Check if the destination file already exists
                        if os.path.exists(destination):
                            # Compare the files using mne
                            # This will check if the files are identical
                            
                            # check = mne.viz.compare_fiff(source, destination,
                            #                              show=False)

                            check = subprocess.run(f'mne compare_fiff {source} {destination}', shell=True, capture_output=True)

                            if check.returncode == 0:
                                continue

                            else:
                                # raw = mne.io.read_raw_fif(source, allow_maxshield=True, verbose='error')
                                
                                # raw.save(destination, overwrite=True, verbose='error')
                                
                                copy_if_newer_or_larger(source, destination)
                                
                                log(f'Update {source} --> {destination}', logfile=log_file, logpath=log_path)
                                

                        # Save the file to the destination  
                        else:
                            # raw = mne.io.read_raw_fif(source, allow_maxshield=True, verbose='error')
                            # raw.save(destination, overwrite=True, verbose='error')
                            copy_if_newer_or_larger(source, destination)

                            log(f'Copy {source} --> {destination}', logfile=log_file, logpath=log_path)
                    else:
                        if os.path.exists(destination):
                            check = filecmp.cmp(source, destination, shallow=True)

                            if check:
                                continue
                            else:
                                # For other files, just copy them
                                copy_if_newer_or_larger(source, destination)
                                log(f'Update {source} --> {destination}', logfile=log_file, logpath=log_path)
                        else:
                            copy_if_newer_or_larger(source, destination)
                            log(f'Copy {source} --> {destination}', logfile=log_file, logpath=log_path)
            
            if new_hedscan_files: 
                        
                for file in hedscan_files:
                    # Copy the file to the local directory
                    source = f'{kaptah}/sub-{subject}/{file}'
                    file
                    new_file = f"{file.split('file-')[-1]}"
                    destination = f'{hedscan_dst_path}/{new_file}'
                    
                    if os.path.isdir(source):
                        copytree(source, destination, dirs_exist_ok=True)
                        continue
                    
                    if '.fif' in file and not file_contains(file, headpos_patterns):    
                        
                        # If the file is a .fif file, use mne to read and write it
                        # Check if the destination file already exists
                        if os.path.exists(destination):
                            # Compare the files using mne
                            # This will check if the files are identical
                            check = subprocess.run(f'mne compare_fiff {source} {destination}', shell=True, capture_output=True)
                            if check.returncode == 0:
                                continue
                            else:
                                
                                raw = mne.io.read_raw_fif(source, allow_maxshield=True, verbose='error')
                                
                                raw.save(destination, overwrite=True, verbose='error')
                                log(f'Update {source} --> {destination}', logfile=log_file, logpath=log_path)
                        # Save the file to the destination  
                        else:
                            raw = mne.io.read_raw_fif(source, allow_maxshield=True, verbose='error')
                            raw.save(destination, overwrite=True, verbose='error')
                            log(f'Copy {source} --> {destination}', logfile=log_file, logpath=log_path)
                    else:
                        if os.path.exists(destination):
                            check = filecmp.cmp(source, destination, shallow=True)
                        
                            if check:
                                continue
                            else:
                                # For other files, just copy them
                                copy_if_newer_or_larger(source, destination)
                                log(f'Update {source} --> {destination}', logfile=log_file, logpath=log_path)
                        else:
                            copy_if_newer_or_larger(source, destination)
                            log(f'Copy {source} --> {destination}', logfile=log_file, logpath=log_path)

