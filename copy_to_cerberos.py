from glob import glob
from mne.io import read_raw, read_info
import re
import json
import argparse
import yaml
from copy import deepcopy
import os
from shutil import copy2, copytree
from typing import Union
from datetime import datetime
import filecmp
import pandas as pd

sinuhe_root = 'neuro/data/sinuhe'
kaptah_root = 'neuro/data/kaptah'
local_root = 'neuro/data/local'

from utils import (
    log,
    headpos_patterns,
    proc_patterns,
    file_contains,
    askForConfig
)

global local_dir

def get_parameters(config):
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
    
    copy_config = deepcopy(config_dict['project'])
    
    return copy_config

def copy_if_newer_or_larger(source, destination):
    """
    Copy file from source to destination if source is newer or larger than destination.
    """
    if not os.path.exists(destination):
        if os.path.isdir(source):
            copytree(source, destination)
        else:
            copy2(source, destination)
    elif (os.path.getmtime(source) > os.path.getmtime(destination) or
    os.path.getsize(source) > os.path.getsize(destination)):
        if os.path.isdir(source):
            copytree(source, destination, dirs_exist_ok=True)
        else:
            copy2(source, destination)

def check_fif(source, destination):

    info_src = read_info(source, verbose='error')
    info_dst = read_info(destination, verbose='error')

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
    raw_src = read_raw(source, allow_maxshield=True, verbose='error')
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

def copy_from_sinuhe(config, check_existing=False):
    # Create the local directory if it doesn't exist
    local_dir = config['squidMEG']
    if not os.path.exists(local_dir):
        os.makedirs(local_dir, exist_ok=True)

    # Create log directory in the project root (parent of local_dir)
    project_root = os.path.dirname(local_dir)
    log_path = os.path.join(project_root, 'log')
    os.makedirs(log_path, exist_ok=True)
    logfile = config.get('Logfile', 'pipeline_log.log')
    
    new_files = True

    if not config['sinuhe_raw']:
        log('Copy', 'No TRIUX directory defined', 'warning', logfile=logfile, logpath=log_path)

    elif not os.path.isdir(config['sinuhe_raw']):
        log('Copy', f"{config['sinuhe_raw']} is not a directory", 'error', logfile=logfile, logpath=log_path)

    elif not glob('*', root_dir=config['sinuhe_raw']):
        log('Copy', f"{config['sinuhe_raw']} is empty", 'warning', logfile=logfile, logpath=log_path)
    
    else:
        sinuhe = config['sinuhe_raw']
        natmeg_subjects  = [s for s in glob(f'NatMEG_*', root_dir=sinuhe) if os.path.isdir(f'{sinuhe}/{s}')]
        
        other_files_and_dirs = [f for f in glob(f'*', root_dir=sinuhe) if f not in natmeg_subjects]
        
        subjects = sorted(list(set([s.split('_')[-1] for s in natmeg_subjects])))
        
        for item in other_files_and_dirs:
            source = f'{sinuhe}/{item}'
            destination = f'{local_dir}/{item}'
            if os.path.exists(destination):
                check = filecmp.cmp(source, destination, shallow=True)
                if check:
                    continue
                else:
                    copy_if_newer_or_larger(source, destination)
            else:
                copy_if_newer_or_larger(source, destination)
        for subject in subjects:
            sessions = sorted([session for session in glob('*', root_dir = f'{sinuhe}/NatMEG_{subject}')
            if os.path.isdir(f'{sinuhe}/NatMEG_{subject}/{session}') and re.match(r'^\d{6}$', session)
            ])
            sinuhe_subject_dir = f'{sinuhe}/NatMEG_{subject}'
            
            other_files_and_dirs = [f for f in glob(f'*', root_dir=sinuhe_subject_dir) if f not in sessions]
            
            local_subject_dir = f'{local_dir}/sub-{subject}'
            if not os.path.exists(local_subject_dir):
                os.makedirs(local_subject_dir, exist_ok=True)
        
            for item in other_files_and_dirs:
                source = f'{sinuhe_subject_dir}/{item}'
                destination = f'{local_subject_dir}/{item}'
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
                
                if not new_triux_files:
                    new_files = False
                    continue

                # First copy files that dont exist:
                for file in new_triux_files:
                    source = f'{sinuhe}/NatMEG_{subject}/{session}/meg/{file}'
                    destination = f'{triux_dst_path}/{file}'
                    print(f'Trying {source} --> {destination}')

                    if '.fif' in file and not file_contains(file, headpos_patterns + ['ave.fif']) and check_size_fif:
                        # Check if split
                        if not file_contains(file, [r'-\d+.fif'] + [r'-\d+_' + p for p in proc_patterns]):
                            try:
                                raw = read_raw(source, allow_maxshield=True, verbose='error')
                                raw.save(destination, overwrite=True, verbose='error')
                                log('Copy', f'Copied (split if > 2GB) {source} --> {destination}', logfile=logfile, logpath=log_path)
                            except Exception as e:
                                copy_if_newer_or_larger(source, destination)
                                log('Copy', f'{source} --> {destination} {e}', 'warning',logfile=logfile, logpath=log_path)
                            continue
                    else:
                        copy_if_newer_or_larger(source, destination)
                        log('Copy', f'Copied {source} --> {destination}', logfile=logfile, logpath=log_path)

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
                            log('Copy', f'Updated {source} --> {destination}', logfile=logfile, logpath=log_path)
        if not new_files:
            log('Copy', f'No new TRIUX files to copy', logfile=logfile, logpath=log_path)

def copy_from_kaptah(config: Union[str, dict], check_existing=False):
    
    local_dir = config['opmMEG']
    if not os.path.exists(local_dir):
        os.makedirs(local_dir, exist_ok=True)

    # Create log directory in the project root (parent of local_dir)
    project_root = os.path.dirname(local_dir)
    log_path = os.path.join(project_root, 'log')
    os.makedirs(log_path, exist_ok=True)
    logfile = config.get('Logfile', 'pipeline_log.log')
    new_files = True

    if not config['kaptah_raw']:
        log('Copy', 'No Hedscan directory defined', 'warning', logfile=logfile, logpath=log_path)

    elif not os.path.isdir(config['kaptah_raw']):
        log('Copy', f"{config['kaptah_raw']} is not a directory", 'error', logfile=logfile, logpath=log_path)
    
    elif not glob('*', root_dir=config['kaptah_raw']):
        log('Copy', f"{config['kaptah_raw']} is empty", 'warning', logfile=logfile, logpath=log_path)

    else:

        kaptah = config['kaptah_raw']
        kaptah_subjects  = [s for s in glob(f'sub-*', root_dir=kaptah) if os.path.isdir(f'{kaptah}/{s}')]
        
        other_files_and_dirs = [f for f in glob(f'*', root_dir=kaptah) if f not in kaptah_subjects]
        
        subjects = sorted(list(set([s.split('-')[-1] for s in kaptah_subjects])))
        
        for item in other_files_and_dirs:
            source = f'{kaptah}/{item}'
            destination = f'{local_dir}/{item}'
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
                
                if not new_hedscan_files:
                    new_files = False
                    continue

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
                                raw = read_raw(source, allow_maxshield=True, verbose='error')
                                raw.save(destination, overwrite=True, verbose='error')
                                log('Copy', f'Copied (split if > 2GB) {source} --> {destination}', logfile=logfile, logpath=log_path)
                            except Exception as e:
                                log('Copy', f'{source} !!! {destination} {e}', 'error', logfile=logfile, logpath=log_path)
                        else:
                            continue
                    else:
                        copy_if_newer_or_larger(source, destination)
                        log('Copy', f'Copied {source} --> {destination}', logfile=logfile, logpath=log_path)
                
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
                            log('Copy', f'Updated {source} --> {destination}', logfile=logfile, logpath=log_path)
        if not new_files:         
            log('Copy', 'No new HEDSCAN files to copy', logfile=logfile, logpath=log_path)


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
        if not config_file or not os.path.exists(config_file):
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
        if os.path.exists(config_file):
            config = get_parameters(config_file)
            print(f'Using configuration file: {config_file}')
        else:
            print(f'Configuration file not found: {config_file}')
            return

    # If config is already a dict, use it as-is
    copy_from_sinuhe(config, check_existing=False)
    copy_from_kaptah(config, check_existing=False)
    return True

if __name__ == "__main__":
    main()
            