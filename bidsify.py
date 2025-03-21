# #!/opt/miniconda3/envs/mne/bin/python
# #!/home/natmeg/miniforge3/envs/mne/bin/python
import pandas as pd
import json
import re
import os
from shutil import copy2
from os.path import exists, basename
import sys
from glob import glob
import numpy as np
import tkinter as tk
from tkinter.filedialog import askopenfilename
import argparse
from datetime import datetime

from mne_bids import (
    BIDSPath,
    write_raw_bids,
    read_raw_bids,
    update_sidecar_json,
    make_dataset_description,
    write_meg_calibration,
    write_meg_crosstalk,
    print_dir_tree,
    find_matching_paths
    )
import mne

###############################################################################
# Global variables
###############################################################################
noise_patterns = ['empty', 'noise', 'Empty']
proc_patterns = ['tsss', 'sss', 'corr', 'ds', 'mc', 'avgHead']
exclude_patterns = [r'-\d\.fif', '_trans', 'avg.fif']

InstitutionName = 'Karolinska Institutet'
InstitutionAddress = 'Nobels vag 9, 171 77, Stockholm, Sweden'
InstitutionDepartmentName = 'Department of Clinical Neuroscience (CNS)'

###############################################################################
# Functions: Create or fill templates: dataset description, participants info
###############################################################################

def log(
    message: str,
    level: str='info',
    logfile: str='log.tsv',
    logpath: str='.'):
    """
    Print a message to the console and write it to a log file.
    Parameters
    ----------
    message : str
        The message to print and write to the log file.
    level : str
        The log level. Can be 'info', 'warning', or 'error'.
    logfile : str
        The name of the log file.
    logpath : str
        The path to the log file.
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

    # Write the message to the log file
    with open(f'{logpath}/{logfile}', 'a') as f:
        f.write(f"[{level.upper()}]\t{timestamp}\t{message}\n")
    print(formatted_message)


def create_dataset_description(
    path_BIDS: str='.',
    overwrite=False):
    """_summary_

    Args:
        path_BIDS (str, required): _description_. Defaults to '.'.
        overwrite (bool, required): _description_. Defaults to False.
    Returns:
        None
    """
    
    # Make sure the BIDS directory exists and create it if it doesn't
    os.makedirs(path_BIDS, exist_ok=True)
    
    # Define the path to the dataset_description.json file
    file_bids = f'{path_BIDS}/dataset_description.json'

    # Check and load if exists
    if exists(file_bids):
        with open(file_bids, 'r') as f:
            desc_data_bids = json.load(f)

    # Create empty dataset description if not exists
    else:
        desc_data_bids = {
            'Name': '',
            'BIDSVersion': '1.7.0',
            'DatasetType': 'raw',
            'License': '',
            'Authors': '',
            'Acknowledgements': '',
            'HowToAcknowledge': '',
            'Funding': '',
            'EthicsApprovals': '',
            'ReferencesAndLinks': '',
            'DatasetDOI': ''
        }

    # Open UI to fill the dataset description if not exists or overwrite is True
    if not exists(file_bids) or overwrite:
        
        # Create a new Tkinter window
        root = tk.Tk()
        root.title('BIDSify Dataset Description')
        root.geometry('750x500')
        
        # Main frame
        frame = tk.LabelFrame(root, text='Dataset description')
        frame.grid(row=0, column=0,
                    ipadx=5, ipady=5, sticky='e')
        
        # Buttons frame
        button_frame = tk.LabelFrame(root, text="", padx=10, pady=10, border=0)
        button_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)

        # Create labels and entries for each field in the dataset description
        keys = []
        entries = []
        for i, key in enumerate(desc_data_bids):
            val = desc_data_bids[key]
            # Add doi: if not present, MNE-BIDS requires it
            if 'DatasetDOI' in key:
                if 'doi:' not in val:
                    val = 'doi:' + val
            label = tk.Label(frame, text=key).grid(row=i, column=0, sticky='e')
            entry = tk.Entry(frame, width=30)
            entry.grid(row=i, column=1)
            entry.insert(0, val)
            keys.append(key)
            entries.append(entry)

        # Create buttons to save or cancel the dataset description
        def cancel():
            root.destroy()
            print('Closed')

        def save():
            desc_data = {key: entry.get() for key, entry
                         in zip(keys, entries)}
            make_dataset_description(
            path=path_BIDS,
            name=desc_data['Name'],
            dataset_type=desc_data['DatasetType'],
            data_license=desc_data['License'],
            authors=desc_data['Authors'],
            acknowledgements=desc_data['Acknowledgements'],
            how_to_acknowledge=desc_data['HowToAcknowledge'],
            funding=desc_data['Funding'],
            ethics_approvals=desc_data['EthicsApprovals'],
            references_and_links=desc_data['ReferencesAndLinks'],
            doi=desc_data['DatasetDOI'],
            overwrite=True
            )
            print(f'Saving BIDS parameters to {file_bids}')

            root.destroy()

        save_button = tk.Button(
            button_frame,
            text="Save", command=save)
        save_button.grid(row=0, column=0)

        cancel_button = tk.Button(
            button_frame,
            text="Cancel", command=cancel)
        cancel_button.grid(row=0, column=2)

        # Start GUI loop
        root.mainloop()


def create_participants_files(
    path_BIDS: str='.',
    overwrite=False):
    # check if participants.tsv and participants.json files is available or create a new one with default fields
    output_path = os.path.join(path_BIDS)
    os.makedirs(output_path, exist_ok=True)
    
    tsv_file = f'{output_path}/participants.tsv'
    if not exists(tsv_file) or overwrite:
        # create default fields participants.tsv
        participants = glob('NatMEG*', root_dir=output_path)
        # create empty table with 4 columns (participant_id, sex, age)
        df = pd.DataFrame(columns=['participant_id', 'sex', 'age', 'group'])
        
        df.to_csv(f'{output_path}/participants.tsv', sep='\t', index=False)
        print(f'Writing {output_path}/participants.tsv')

    json_file = os.path.join(output_path, 'participants.json')

    if not exists(json_file) or overwrite:
        participants_json = {
            "participant_id": {
                "Description": "Unique participant identifier"
            },
            "sex": {
                "Description": "Biological sex of participant. Self-rated by participant",
                "Levels": {
                    "M": "male",
                    "F": "female"
                }
            },
            "age": {
                "Description": "Age of participant at time of MEG scanning",
                "Units": "years"
            },
            "group": {
                "Description": "Group of participant. By default everyone is in control group",
            }
        }

        with open(f'{output_path}/participants.json', 'w') as f:
            json.dump(participants_json, f, indent=4)
        print(f'Writing {output_path}/participants.json')

###############################################################################
# Help functions
###############################################################################

def load_config_file(
    json_name: str = 'default_config.json'):
    
    """_summary_
    
    
    """

    # Check if the configuration file exists and if so load
    if exists(json_name):
        with open(json_name, 'r') as f:
            config_dict = json.load(f)
    
    # Create default configuration file
    else:
        config_dict = {
            'squidMEG': '/neuro/sinuhe/',
            'opmMEG': '',
            'BIDS': '',
            'Calibration': '/neuro/databases/sss/sss_cal.dat',
            'Crosstalk': '/neuro/databases/ctc/ct_sparse.fif',
            'Dataset_description': '',
            'Participants': '',
            'Participants mapping file': '',
            'Original subjID': '',
            'New subjID': '',
            'Original sessionID': '',
            'New sessionID': '',
            'Overwrite': 'off'  
        }

    # Create a new Tkinter window
    root = tk.Tk()
    root.title('BIDSify Configuration')
    root.geometry('500x500')
    
    # Main frame
    frame = tk.LabelFrame(root, text='BIDSify Configuration')
    frame.grid(row=0, column=0,
                ipadx=5, ipady=5, sticky='e')
    
    # Buttons frame
    button_frame = tk.LabelFrame(root, text="", padx=10, pady=10, border=0)
    button_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
    
    # Create labels and entries for each field in the configuration
    chb = {}
    keys = []
    entries = []
    for i, key in enumerate(config_dict):
        val = config_dict[key]
        
        label = tk.Label(frame, text=key).grid(row=i, column=0, sticky='e')

        if val in ['on', 'off']:
            chb[key] = tk.StringVar()
            chb[key].set(val)
            check_box = tk.Checkbutton(frame,
                                       variable=chb[key], onvalue='on', offvalue='off',
                                       text='')
            
            check_box.grid(row=i, column=1, padx=2, pady=2, sticky='w')
            entry = chb[key]
        else:
            entry = tk.Entry(frame, width=30)
            entry.grid(row=i, column=1)
            entry.insert(0, val)
        
        keys.append(key)
        entries.append(entry)
    
    # Create buttons to save or cancel the configuration
    def cancel():
            root.destroy()
            print('Closed')

    def save():
        config_dict = {}

        for key, entry in zip(keys, entries):
            if ', ' in entry.get():
                config_dict[key] = [x.strip() for x in entry.get().split(', ') if x.strip()]
            else:
                config_dict[key] = entry.get()
            
        # Replace with save data
        with open(json_name, 'w') as output_file:
            json.dump(config_dict, output_file, indent=4, default=list)

        root.destroy()
        print(f'Saving BIDS parameters to {json_name}')

    save_button = tk.Button(button_frame,
                            text="Save", command=save)
    save_button.grid(row=0, column=0)

    cancel_button = tk.Button(button_frame,
                            text="Cancel", command=cancel)
    cancel_button.grid(row=0, column=2)

    # Start GUI loop
    root.mainloop()



def select_config_file(file_config: str=None):
    """_summary_

    Args:
        file_config (str, optional): _description_. Defaults
            to None.

    Returns:
        dict: dictionary with the configuration parameters
    """

    # Check if the file is defined or ask for it
    if not file_config:
        file_config = askopenfilename(title='Select config file or press Cancel to create new one', filetypes=[('JSON files', '*.json')])
        
        # If Cancel, open dialog to create a new one
        if file_config:
            load_config_file(file_config)
        else:
            load_config_file()
    
    # Load the configuration file if defined
    else:
        try:
            with open(file_config, 'r') as f:
                data = json.load(f)

            return data
        except Exception as e:
            print(f'Error loading configuration file: {e}')
            sys.exit(1)

def update_sidecar(bids_path: BIDSPath):
    """_summary_

    Args:
        bids_path (BIDSPath): _description_
    Returns:
        None
    """
    # Find associated sidecar file
    sidecar_path = bids_path.copy().update(
        check=True,
        split=None,
        extension='.json')

    # Add institution name, department and address
    sidecar_updates = {
            'InstitutionName': InstitutionAddress,
            'InstitutionDepartmentName': InstitutionDepartmentName,
            'InstitutionAddress': InstitutionName
            }
    
    # Add Dewar position and associated empty room
    if bids_path.datatype == 'meg' and bids_path.acquisition == 'squid':
        info = mne.io.read_info(bids_path.fpath)
        if info['gantry_angle'] > 0:
            dewar_pos = f'upright ({int(info["gantry_angle"])} degrees)'
        else:
            dewar_pos = f'supine ({int(info["gantry_angle"])} degrees)'
        sidecar_updates['DewarPosition'] = dewar_pos
        
        if bids_path.task not in ['noisebefore', 'noiseafter']: 
            er_bids_paths = find_matching_paths(
                            bids_path.root, 
                            subjects=bids_path.subject,
                            sessions=bids_path.session,
                            tasks = ['noisebefore', 'noiseafter'],
                            acquisitions = 'squid',
                            extensions='.fif')
            
            sidecar_updates['AssociatedEmptyRoom'] = [basename(er) for er in er_bids_paths]
    
    # Update Manufacturer FieldLine for OPM data
    if bids_path.datatype == 'meg' and bids_path.acquisition == 'opm':
        sidecar_updates["Manufacturer"] = "FieldLine"
        
    update_sidecar_json(bids_path=sidecar_path, 
                        entries=sidecar_updates)

    message = f'{sidecar_path.basename} updated'
    print(message)

def file_contains(file: str, pattern: list):
    return bool(re.compile('|'.join(pattern)).search(file))


def add_channel_parameters(
    bids_tsv: str,
    opm_tsv: str):

    if exists(opm_tsv):
        orig_df = pd.read_csv(opm_tsv, sep='\t')
        bids_df = pd.read_csv(bids_tsv, sep='\t')
        
        # Compare file with file in BIDS folder

        add_cols = [c for c in orig_df.columns
                    if c not in bids_df.columns] + ['name']

        if not np.array_equal(
            orig_df, bids_df):
            
            bids_df = bids_df.merge(orig_df[add_cols], on='name', how='outer')

            bids_df.to_csv(bids_tsv, sep='\t', index=False)
    print(f'Adding channel parameters to {basename(bids_tsv)}')


def extract_info_from_filename(file_name: str):
    
    """_summary_
    
    Function to clean up filenames and extract
    
    Args:
        file_name (str, required): _description_
        
    Returns:
        dict: 
            filename (str): _description_
            participant (str): _description_
            task (str): _description_
            processing (list): _description_
            datatypes (list): _description_
            extension (str): _description_
    """
    
    # Extract participant, task, processing, datatypes and extension
    participant = re.search(r'(NatMEG_|sub-)(\d+)', file_name).group(2)
    extension = '.' + re.search(r'\.(.*)', file_name).group(1)
    datatypes = list(set([r.lower() for r in re.findall(r'(meg|raw|opm|eeg|behav)', basename(file_name), re.IGNORECASE)]))
    
    proc = [p for p in proc_patterns if p in basename(file_name)]
    if 'tsss' in proc and 'sss' in proc:
        proc.remove('sss')
    
    exclude_from_task = '|'.join(['NatMEG_'] + ['sub-'] + ['proc']+ datatypes + [participant] + [extension] + proc + ['\\+'] + ['\\-'])
    
    task = re.sub(exclude_from_task, '', basename(file_name), flags=re.IGNORECASE)
    task = [t for t in task.split('_') if t]
    if len(task) > 1:
        task = ''.join([t.title() for t in task])
    else:
        task = task[0]
    
    info_dict = {
        'filename': file_name,
        'participant': participant,
        'task': task,
        'processing': proc,
        'datatypes': datatypes,
        'extension': extension
    }
    
    return info_dict


def copy_eeg_to_meg(file_name: str, bids_path: BIDSPath):
    
    raw = mne.io.read_raw_fif(file_name, allow_maxshield=True, verbose='error')
    
    # Confirm that the file is EEG
    if not 'meg' in set(raw.info.get_channel_types()):
       bids_json = find_matching_paths(bids_path.root,
                            tasks=bids_path.task,
                            suffixes='eeg',
                            extensions='.json')[0]
       bids_eeg = bids_json.copy().update(datatype='meg',
                                          extension='.fif')
       
       raw.save(bids_eeg.fpath, overwrite=True)

       json_from = bids_json.fpath
       json_to = bids_json.copy().update(datatype='meg').fpath
       
       copy2(json_from, json_to)
       
       # Copy CapTrak files
       CapTrak = find_matching_paths(bids_eeg.root, spaces='CapTrak')
       for old_cap in CapTrak:
           new_cap = old_cap.copy().update(datatype='meg')
           if not exists(new_cap):
               copy2(old_cap, new_cap)

def get_desc_from_raw(file_name):
    info = mne.io.read_info(file_name, verbose='error')
    
    update_dict = {
        
    }

def bidsify_sqid_meg(
    config_dict: dict,
    overwrite=False):
    
    """
    For each participant and session within MEG folder, move the files to BIDS correspondent folder
    or create a new one if the session does not match. Change the name of the files into BIDS format.
    """
    path_MEG = config_dict['squidMEG']
    path_BIDS = config_dict['BIDS']
    calibration = config_dict['Calibration']
    crosstalk = config_dict['Crosstalk']
    participant_mapping = config_dict['Participants mapping (csv)']
    old_subj_id = config_dict['Original subjID name']
    new_subj_id = config_dict['New subjID name']
    old_session = config_dict['Original session name']
    new_session = config_dict['New session name']
    
    error_files_list = []
    if participant_mapping:
        pmap = pd.read_csv(participant_mapping, dtype=str)
    if path_MEG != '' and str(path_MEG) != '()':
        print('Processing:')
        for participant in glob('NatMEG*', root_dir=path_MEG):
            subject = participant.strip('NatMEG_')
            participant_path = os.path.join(path_MEG, participant)
            print(f'|{path_MEG}/')
            print(f'|--- {participant}/')
            if participant_mapping:
                subject = pmap.loc[pmap[old_subj_id] == subject, new_subj_id].values[0]
            
            for session in glob('*', root_dir=participant_path):
                session_path = os.path.join(participant_path, session)
                print(f'|------ {session}/')
                all_fifs_files = glob(f'*.fif', root_dir=f'{session_path}/meg')
                
                if participant_mapping:
                    session = pmap.loc[pmap[old_session] == session, new_session].values[0]

                # Add calibration and cross talk
                bids_path = BIDSPath(
                        subject=subject,
                        datatype='meg',
                        session=session,
                        root=f'{path_BIDS}',
                    )

                if not bids_path.meg_calibration_fpath:
                    write_meg_calibration(calibration, bids_path)
                if not bids_path.meg_crosstalk_fpath:
                    write_meg_crosstalk(crosstalk, bids_path)

                empty_fname = []
                raw_start_fnames = []
                mxf_start_fnames = []
                for raw_file in all_fifs_files:
                    if file_contains(raw_file, noise_patterns):
                        empty_fname.append(raw_file)
                    if not file_contains(raw_file, exclude_patterns + noise_patterns + proc_patterns):
                        raw_start_fnames.append(raw_file)
                    if file_contains(raw_file, proc_patterns) and not       file_contains(raw_file, noise_patterns + exclude_patterns):
                        mxf_start_fnames.append(raw_file)
                
                # Empty rooms files
                try:
                    noise_bids_files = []
                    for er_file in empty_fname:
                        if er_file:
                            print(f'|--------- {er_file}')
                            try:
                                er_task = f'noise{re.search("before|after", er_file).group()}'
                            except Exception:
                                er_task = 'noise'
                            
                            er_file_name = f'{session_path}/meg/{er_file}'
                            
                            er_raw = mne.io.read_raw_fif(
                                er_file_name,
                                allow_maxshield=True,
                                verbose='error')
                            
                            ch_types = set(er_raw.info.get_channel_types())
                            
                            if 'mag' in ch_types:
                                datatype = 'meg'
                                extension = '.fif'
                            elif 'eeg' in ch_types:
                                datatype = 'eeg'

                            er_bids_path = BIDSPath(
                                subject = subject,
                                datatype='meg',
                                session = session,
                                task=er_task,
                                acquisition='squid',
                                suffix='meg',
                                root=path_BIDS
                            )
                            if not exists(er_bids_path.fpath) or overwrite:
                                write_raw_bids(
                                    raw=er_raw,
                                    bids_path=er_bids_path, 
                                    empty_room=None,
                                    events=None,
                                    overwrite=True
                                    )
                                noise_bids_files.append(er_bids_path.basename)

                                update_sidecar(er_bids_path)
                                
                                if datatype == 'eeg':
                                    copy_eeg_to_meg(er_file_name, er_bids_path)
                                
                                log(
                                    f'{er_file_name} -> {er_bids_path}',
                                    level='info',
                                    logfile='log.tsv',
                                    logpath=path_BIDS
                                    )
                except Exception as e:
                    error_files_list.append(f'{session_path}/meg/{er_file}')

                # Task files
                try:
                    for raw_file in raw_start_fnames:
                        print(f'|--------- {raw_file}')
                        # Extract datatype and task
                        for dt in ['meg', 'raw', 'opm', 'eeg']:
                            if dt in basename(raw_file).lower():
                                datatype = dt
                                break
                        
                        file_name = f'{session_path}/meg/{raw_file}'
                        
                        info_dict = extract_info_from_filename(file_name)
                        
                        task = info_dict.get('task')
                        
                        raw = mne.io.read_raw_fif(file_name, allow_maxshield=True, verbose='error')
                        
                        ch_types = set(raw.info.get_channel_types())
                        
                        if 'mag' in ch_types:
                            datatype = 'meg'
                            extension = '.fif'
                        elif 'eeg' in ch_types:
                            datatype = 'eeg'

                        bids_path = BIDSPath(
                            subject=subject,
                            session=session,
                            datatype=datatype,
                            task=task,
                            acquisition='squid',
                            root=f'{path_BIDS}',
                            suffix=datatype
                        )

                        # Write raw BIDS data
                        if not exists(bids_path.fpath) or overwrite:
                            write_raw_bids(
                                raw=raw,
                                bids_path=bids_path,
                                empty_room=None,
                                events=None,
                                overwrite=True,
                                verbose='error'
                            )
                            update_sidecar(er_bids_path)
                            
                            if datatype == 'eeg':
                                copy_eeg_to_meg(file_name, bids_path)
                            
                            log(
                            f'{file_name} -> {bids_path}',
                            level='info',
                            logfile='log.tsv',
                            logpath=path_BIDS
                            )
                except Exception as e:
                    error_files_list.append(f'{session_path}/meg/{raw_file}')
            
                # Task files (maxfiltered)
                try:
                    for raw_file in mxf_start_fnames:
                        print(f'|--------- {raw_file}')
                        # Extract datatype and task
                        for dt in ['meg', 'raw', 'opm', 'eeg']:
                            if dt in basename(raw_file).lower():
                                datatype = dt
                                break
                        
                        file_name = f'{session_path}/meg/{raw_file}'
                        
                        info_dict = extract_info_from_filename(file_name)
                        
                        task = info_dict.get('task')
                        proc = '+'.join(info_dict.get('processing'))
                        
                        raw = mne.io.read_raw_fif(file_name, allow_maxshield=True, verbose='error')
                        
                        ch_types = set(raw.info.get_channel_types())
                        
                        if 'mag' in ch_types:
                            datatype = 'meg'
                        elif 'eeg' in ch_types:
                            datatype = 'eeg'

                        # might be different number the one to always differentiate EEG form MEG

                        bids_path = BIDSPath(
                            subject=subject,
                            session=session,
                            datatype=datatype,
                            task=task,
                            acquisition='squid',
                            root=f'{path_BIDS}',
                            processing=proc,
                            suffix=datatype
                        )

                        # Write raw BIDS data
                        if not exists(bids_path.fpath) or overwrite:
                            write_raw_bids(
                                raw=raw,
                                bids_path=bids_path,
                                empty_room=None,
                                events=None,
                                overwrite=True,
                                verbose='error'
                            )
                            update_sidecar(er_bids_path)
                            
                            if datatype == 'eeg':
                                copy_eeg_to_meg(file_name, bids_path)
                            
                            log(
                            f'{file_name} -> {bids_path}',
                            level='info',
                            logfile='log.tsv',
                            logpath=path_BIDS
                            )
                except Exception as e:
                    error_files_list.append(f'{session_path}/meg/{raw_file}')
            
            if error_files_list:
                print('Error files:')
                for file in error_files_list:
                    log(
                        f'Error processing file: {file}', level='error',
                        logfile='log.tsv',
                        logpath=path_BIDS
                        )


def bidsify_opm_meg(
    config_dict: dict,
    overwrite=False):
    
    """
    For each participant and session within MEG folder, move the files to BIDS correspondent folder
    or create a new one if the session does not match. Change the name of the files into BIDS format.
    """
    path_OPM = config_dict['opmMEG']
    path_BIDS = config_dict['BIDS']
    participant_mapping = config_dict['Participants mapping (csv)']
    old_subj_id = config_dict['Original subjID name']
    new_subj_id = config_dict['New subjID name']
    old_session = config_dict['Original session name']
    new_session = config_dict['New session name']
    
    error_files_list = []
    if participant_mapping:
        pmap = pd.read_csv(participant_mapping, dtype=str)
    if path_OPM != '' and str(path_OPM) != '()':
        print('Processing:')
        for participant in glob('sub*', root_dir=path_OPM):
            subject = participant.strip('sub-')
            participant_path = os.path.join(path_OPM, participant)
            print(f'|{path_OPM}/')
            print(f'|--- {participant}/')
            if participant_mapping:
                subject = pmap.loc[pmap[old_subj_id] == subject, new_subj_id].values[0]

            sessions = list(set([f.split('_')[0][2:] for f in glob('*', root_dir=participant_path)]))
            
            for session in sessions:
                print(f'|------ {session}/')
                all_fifs_files = glob(f'*{session}*.fif', root_dir=f'{participant_path}')
                all_tsv_files = glob(f'*{session}*_channels.tsv', root_dir=f'{participant_path}')

                if participant_mapping:
                    session = pmap.loc[pmap[old_session] == session, new_session].values[0]

                # Add calibration and cross talk
                bids_path = BIDSPath(
                        subject=subject,
                        datatype='meg',
                        session=session,
                        root=f'{path_BIDS}',
                    )

                empty_fname = []
                raw_start_fnames = []
                for raw_file in all_fifs_files:
                    if file_contains(raw_file, noise_patterns):
                        empty_fname.append(raw_file)
                    if not file_contains(raw_file, exclude_patterns + noise_patterns + proc_patterns):
                        raw_start_fnames.append(raw_file)

                # Empty rooms files
                try:
                    noise_bids_files = []
                    for er_file in empty_fname:
                        if er_file:
                            print(f'|--------- {er_file}')
                            try:
                                er_task = f'noise{re.search("before|after", er_file).group()}'
                            except Exception:
                                er_task = 'noise'
                                
                            er_file_name = f'{participant_path}/{er_file}'
                            er_raw = mne.io.read_raw_fif(
                                er_file_name,
                                allow_maxshield=True,
                                verbose='error')

                            er_bids_path = BIDSPath(
                                subject = subject,
                                datatype='meg',
                                session = session,
                                task=er_task,
                                acquisition='opm',
                                suffix='meg',
                                root=path_BIDS
                            )
                            if not exists(er_bids_path.fpath) or overwrite:
                                write_raw_bids(
                                    raw=er_raw,
                                    bids_path=er_bids_path, 
                                    empty_room=None,
                                    events=None,
                                    overwrite=True
                                    )
                                noise_bids_files.append(er_bids_path.basename)
                                
                                # Check if there is an associated channels tsv file and copy it
                                er_file_name_tsv = er_file_name.replace('_raw.fif', '_channels.tsv')
                                er_bids_path_tsv = er_bids_path.copy().update(
                                            suffix='channels',
                                            extension='.tsv')
                                
                                add_channel_parameters(er_bids_path_tsv, er_file_name_tsv)                        
                                update_sidecar(er_bids_path)

                                log(
                                    f'{er_file_name} -> {er_bids_path}',
                                    level='info',
                                    logfile='log.tsv',
                                    logpath=path_BIDS
                                    )
                except Exception as e:
                    error_files_list.append(f'{er_file_name}')

                # Task files
                try:
                    for raw_file in raw_start_fnames:
                        print(f'|--------- {raw_file}')

                        task = re.split('_', basename(raw_file), flags=re.IGNORECASE)[-2].strip('file-')
                        task = re.split('opm', task, flags=re.IGNORECASE)[0]

                        if '_' in task:
                            task = [t for t in task.split('_') if t]
                            if isinstance(task, list):
                                task = ''.join(task)
                        
                        file_name = f'{participant_path}/{raw_file}'

                        raw = mne.io.read_raw_fif(file_name, allow_maxshield=True, verbose='error')
                        
                        ch_types = set(raw.info.get_channel_types())
                        
                        if 'mag' in ch_types:
                            datatype = 'meg'
                            extension = 'fif'
                        elif 'eeg' in ch_types:
                            datatype = 'eeg'

                        # might be different number the one to always differentiate EEG form MEG

                        bids_path = BIDSPath(
                            subject=subject,
                            session=session,
                            datatype=datatype,
                            task=task,
                            acquisition='opm',
                            root=f'{path_BIDS}',
                            suffix=datatype
                        )

                        if not exists(bids_path.fpath) or overwrite:
                        # Write raw BIDS data
                            write_raw_bids(
                                raw=raw,
                                bids_path=bids_path,
                                empty_room=None,
                                events=None,
                                overwrite=True,
                                verbose='error'
                            )
                            
                            file_name_tsv = file_name.replace('_raw.fif', '_channels.tsv')
                            bids_path_tsv = bids_path.copy().update(
                                        suffix='channels',
                                        extension='.tsv')
                                
                            add_channel_parameters(bids_path_tsv, file_name_tsv)  

                            update_sidecar(bids_path)
                            
                            log(
                            f'{file_name} -> {bids_path}',
                            level='info',
                            logfile='log.tsv',
                            logpath=path_BIDS
                            )
                except Exception as e:
                    error_files_list.append(f'{file_name}')

            if error_files_list:
                print('Error files:')
                for file in error_files_list:
                    log(
                        f'Error processing file: {file}', level='error',
                        logfile='log.tsv',
                        logpath=path_BIDS
                        )

def main():
    parser = argparse.ArgumentParser(description='BIDSify Configuration')
    parser.add_argument('--config', type=str, help='Path to the configuration file')
    args = parser.parse_args()

    if args.config:
        file_config = args.config
    else:
        file_config = None
    # Select BIDS configuration file dialog

    config_dict = select_config_file(file_config)
    
    if config_dict:
        for key, value in config_dict.items():
            print(f"{key}: {value}")
        
        if config_dict['Overwrite'] == 'on':
            overwrite_bids = True
        else:
            overwrite_bids = False
        
        # create dataset description file if the file does not exist or overwrite_bids is True
        create_dataset_description(config_dict['BIDS'], overwrite_bids)

        # create participant files if files don't exist at MEG directory or overwrite_bids is True
        create_participants_files(config_dict['BIDS'], overwrite_bids)
        bidsify_sqid_meg(
            config_dict,
            overwrite_bids
        )
        bidsify_opm_meg(
            config_dict,
            overwrite_bids)
        
        print_dir_tree(config_dict['BIDS'])
    else:
        print('No configuration file selected')
        sys.exit(1)

if __name__ == "__main__":
    main()
