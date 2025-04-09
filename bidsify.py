# #!/opt/miniconda3/envs/mne/bin/python
# #!/home/natmeg/miniforge3/envs/mne/bin/python
import pandas as pd
import json
import re
import os
from shutil import copy2
from os.path import exists, basename, dirname
import sys
from glob import glob
import numpy as np
import tkinter as tk
from tkinter.filedialog import askopenfilename, asksaveasfile
import argparse
from datetime import datetime


# Activate the conda environment 'mne' if not already activated
if "CONDA_DEFAULT_ENV" not in os.environ or os.environ["CONDA_DEFAULT_ENV"] != "mne":
    conda_activate = "/opt/homebrew/Caskroom/miniconda/base/bin/activate"  # Adjust path if necessary
    conda_env = "mne"
    os.execv("/bin/bash", ["bash", "-c", f"source {conda_activate} {conda_env} && python {' '.join(sys.argv)}"])

from mne_bids import (
    BIDSPath,
    write_raw_bids,
    read_raw_bids,
    update_sidecar_json,
    make_dataset_description,
    write_meg_calibration,
    write_meg_crosstalk,
    update_anat_landmarks,
    print_dir_tree,
    find_matching_paths
    )
from mne_bids.utils import _write_json
import mne

###############################################################################
# Global variables
###############################################################################
noise_patterns = ['empty', 'noise', 'Empty']
proc_patterns = ['tsss', 'sss', r'corr\d+', 'ds', 'mc', 'avgHead']
exclude_patterns = [r'-\d+\.fif', '_trans', 'avg.fif']

InstitutionName = 'Karolinska Institutet'
InstitutionAddress = 'Nobels vag 9, 171 77, Stockholm, Sweden'
InstitutionDepartmentName = 'Department of Clinical Neuroscience (CNS)'
global data
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
    edit=False):
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

    # Create empty dataset description if not exists
    if not exists(file_bids):
        make_dataset_description(
            path = path_BIDS,
            name = '',
            dataset_type = 'raw',
            data_license = '',
            authors = '',
            acknowledgements = '',
            how_to_acknowledge = '',
            funding = '',
            ethics_approvals = '',
            references_and_links = '',
            doi = 'doi:<insert_doi>',
            overwrite = True
        )
    with open(file_bids, 'r') as f:
        desc_data_bids = json.load(f)

    # Open UI to fill the dataset description if not exists or overwrite is True
    if edit:
        
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
            text="Save and run", command=save)
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

def defaultBidsConfig():
    data = {
            'squidMEG': '/neuro/data/sinuhe/',
            'opmMEG': '',
            'BIDS': '',
            'Calibration': '/neuro/databases/sss/sss_cal.dat',
            'Crosstalk': '/neuro/databases/ctc/ct_sparse.fif',
            'Dataset_description': '',
            'Participants': '',
            'Participants mapping file': '',
            'Original subjID name': '',
            'New subjID name': '',
            'Original session name': '',
            'New session name': '',
            'Overwrite': 'off'  
        }
    return data


def openBidsConfigUI(json_name: str = None):
    """_summary_
    Creates or opens a JSON file with MaxFilter parameters using a GUI.

    Parameters
    ----------
    default_data : dict, optional
        Default data to populate the GUI fields.

    Returns
    -------
    None
    
    """

    # Check if the configuration file exists and if so load
    if not(json_name):
        data = defaultBidsConfig()
    else:
        with open(json_name, 'r') as f:
            data = json.load(f)
    
    # Create default configuration file

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
    for i, key in enumerate(data):
        val = data[key]
        
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
        data = {}

        for key, entry in zip(keys, entries):
            if ', ' in entry.get():
                data[key] = [x.strip() for x in entry.get().split(', ') if x.strip()]
            else:
                data[key] = entry.get()
            
        # Replace with save data
        save_path = asksaveasfile(defaultextension=".json", filetypes=[("JSON files", "*.json")],
                                  initialdir='/neuro/data/local')
        if save_path:
            with open(save_path.name, 'w') as f:
                json.dump(data, f, indent=4, default=list)
            print(f"Settings saved to {save_path.name}")

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
    return data

def askForBidsConfig():
    """_summary_

    Args:
        file_config (str, optional): _description_. Defaults
            to None.

    Returns:
        dict: dictionary with the configuration parameters
    """
    option = input("Do you want to open an existing BIDS config file or create a new? ([open]/new/cancel): ").strip().lower()
    # Check if the file is defined or ask for it
    if option not in ['o', 'open']:
        if option in ['n', 'new']:
            return 'new'
        elif option in ['c', 'cancel']:
            print('User cancelled')
            sys.exit(1)

    else:
        file_config = askopenfilename(title='Select config file', filetypes=[('JSON files', '*.json')],
                                      initialdir='/neuro/data/local')
        if not file_config:
            print('No BIDS settings file selected. Exiting opening dialog')
            sys.exit(1)
        
        print(f'{file_config} selected')
        return file_config


def update_sidecars(bids_root):
    
    """_summary_

    Args:
        bids_root (str): _description_
    Returns:
        None
    """
    # bids_root = config_dict.get('BIDS')
    # Find all meg files in the BIDS folder, ignore EEG for now
    bids_paths = find_matching_paths(bids_root,
                                     suffixes='meg',
                                    acquisitions=['triux', 'hedscan'],
                                    splits=None,
                                     extensions='.fif')
    # Add institution name, department and address
    institution = {
            'InstitutionName': InstitutionAddress,
            'InstitutionDepartmentName': InstitutionDepartmentName,
            'InstitutionAddress': InstitutionName
            }
    
    for bp in bids_paths:
        acq = bp.acquisition
        proc = bp.processing
        suffix = bp.suffix
        info = mne.io.read_info(bp.fpath, verbose='error')
        bp_json = bp.copy().update(extension='.json', split=None)
        with open(str(bp_json.fpath), 'r') as f:
            sidecar = json.load(f)

        if acq == 'triux' and suffix == 'meg':
            if info['gantry_angle'] > 0:
                dewar_pos = f'upright ({int(info["gantry_angle"])} degrees)'
            else:
                dewar_pos = f'supine ({int(info["gantry_angle"])} degrees)'
            sidecar['DewarPosition'] = dewar_pos
            try:
                sidecar['HeadCoilFrequency'] = [f['coil_freq'] for f in info['hpi_meas'][0]['hpi_coils']]
            except IndexError:
                'No head coil frequency found'
            
            # sidecar['ContinuousHeadLocalization']
            
            # TODO: Add maxfilter and headposition parameters
            if proc:
                print('Processing detected')
                proc_list = proc.split('+')
                max_info = info['proc_history'][0]['max_info']
                
                if file_contains(proc, ['sss', 'tsss']):
                    sss_info = max_info['sss_info']
                    sidecar['SoftwareFilters']['MaxFilterVersion'] = info['proc_history'][0]['creator']
                    sidecar['SoftwareFilters']['SignalSpaceSeparation'] = {
                        'Origin': sss_info['origin'].tolist(),
                        'NComponents': sss_info['nfree'],
                        'HPIGLimit': sss_info['hpi_g_limit'],
                        'HPIDistanceLimit': sss_info['hpi_dist_limit']
                        
                    }
                    if ['tsss'] in proc_list:
                        max_st = max_info['max_st']
                        sidecar['SoftwareFilters']['TemporalSignalSpaceSeparation'] = {
                            'SubSpaceCorrelationLimit': max_st['subspcorr'],
                            'LengtOfDataBuffert': max_st['buflen']
                        }
                
                # sidecar['MaxMovement'] 
                # Add average head position file

        if acq == 'hedscan':
            sidecar['Manufacturer'] = 'FieldLine'
        
        new_sidecar = institution | sidecar
        
        with open(str(bp_json.fpath), 'w') as f:
            json.dump(new_sidecar, f, indent=4)


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
        suffix ='meg',
        extension='.json')

    # Add institution name, department and address
    sidecar_updates = {
            'InstitutionName': InstitutionAddress,
            'InstitutionDepartmentName': InstitutionDepartmentName,
            'InstitutionAddress': InstitutionName
            }
    
    # Add Dewar position and associated empty room
    if bids_path.datatype == 'meg' and bids_path.acquisition == 'triux':
        
        info = mne.io.read_info(bids_path.fpath, verbose='error')
        if info['gantry_angle'] > 0:
            dewar_pos = f'upright ({int(info["gantry_angle"])} degrees)'
        else:
            dewar_pos = f'supine ({int(info["gantry_angle"])} degrees)'
        sidecar_updates['DewarPosition'] = dewar_pos

    if file_contains(bids_path.task.lower(), noise_patterns): 
        find_matching_paths(bids_path.directory)
        match_paths = find_matching_paths(
                        bids_path.directory,
                        acquisitions = bids_path.acquisition,
                        suffixes='meg',
                        extensions='.fif')
        noise_paths = [p for p in match_paths if 'noise' in p.task.lower()]

        sidecar_updates['AssociatedEmptyRoom'] = [basename(er) for er in noise_paths]
    
    # Update Manufacturer FieldLine for OPM data
    if bids_path.datatype == 'meg' and bids_path.acquisition == 'hedscan':
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
    datatypes = list(set([r.lower() for r in re.findall(r'(meg|raw|opm|eeg|behav)', basename(file_name), re.IGNORECASE)] +
                         ['opm' if 'kaptah' in file_name else '']))
    datatypes = [d for d in datatypes if d != '']

    proc = re.findall('|'.join(proc_patterns), basename(file_name))
    
    split = re.search(r'(\-\d+\.fif)', basename(file_name))
    split = split.group(1).strip('.fif') if split else ''
    
    exclude_from_task = '|'.join(['NatMEG_'] + ['sub-'] + ['proc']+ datatypes + [participant] + [extension] + proc  + [split] + ['\\+'] + ['\\-'])
    
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

def generate_new_conversion_table(
    config_dict: dict,
    overwrite=False):
    
    """
    For each participant and session within MEG folder, move the files to BIDS correspondent folder
    or create a new one if the session does not match. Change the name of the files into BIDS format.
    """
    ts = datetime.now().strftime('%Y%m%d')
    path_triux = config_dict['squidMEG']
    path_opm = config_dict['opmMEG']
    path_BIDS = config_dict['BIDS']
    calibration = config_dict['Calibration']
    crosstalk = config_dict['Crosstalk']
    participant_mapping = config_dict['Participants mapping file']
    old_subj_id = config_dict['Original subjID name']
    new_subj_id = config_dict['New subjID name']
    old_session = config_dict['Original session name']
    new_session = config_dict['New session name']
    
    processing_modalities = []
    if path_triux != '' and str(path_triux) != '()':
        processing_modalities.append('triux')
    if path_opm != '' and str(path_opm) != '()':
        processing_modalities.append('hedscan')
    
    processing_schema = {
        'time_stamp': [],
        'run_conversion': [],
        'participant_from': [],
        'participant_to': [],
        'session_from': [],
        'session_to': [],
        'task': [],
        'split': [],
        'run': [],
        'datatype': [],
        'acquisition': [],
        'processing': [],
        'raw_path': [],
        'raw_name': [],
        'bids_path': [],
        'bids_name': []
    }
    
    if participant_mapping:
        mapping_found=True
        try:
            pmap = pd.read_csv(participant_mapping, dtype=str)
        except FileExistsError as e:
            mapping_found=False
            print('Participant file not found, skipping')
    
    
    for mod in processing_modalities:
        if mod == 'triux':
            path = path_triux
            participants = [p for p in glob('NatMEG*', root_dir=path) if os.path.isdir(os.path.join(path, p))]
        elif mod == 'hedscan':
            path = path_opm
            participants = [p for p in glob('sub*', root_dir=path) if os.path.isdir(os.path.join(path, p))]

        for participant in participants:
            
            if mod == 'triux':
                sessions = [session for session in glob('*', root_dir=os.path.join(path, participant)) if os.path.isdir(os.path.join(path, participant, session))]
            elif mod == 'hedscan':
                sessions = list(set([f.split('_')[0][2:] for f in glob('*', root_dir=os.path.join(path, participant))]))

            for date_session in sessions:
                
                session = date_session
                
                if mod == 'triux':
                    all_fifs = sorted(glob('*.fif', root_dir=os.path.join(path, participant, date_session, 'meg')))
                elif mod == 'hedscan':
                    all_fifs = sorted(glob('*.fif', root_dir=os.path.join(path, participant)))

                for file in all_fifs:
                    
                    if mod == 'triux':
                        full_file_name = os.path.join(path, participant, date_session, 'meg', file)
                    elif mod == 'hedscan':
                        full_file_name = os.path.join(path, participant, file)
                    
                    if exists(full_file_name):
                        info_dict = extract_info_from_filename(full_file_name)
                    
                    task = info_dict.get('task')
                    proc = '+'.join(info_dict.get('processing'))
                    datatypes = '+'.join([d for d in info_dict.get('datatypes') if d != ''])
                    subject = info_dict.get('participant')
                    split = info_dict.get('split')
                    run = ''
                    
                    if participant_mapping and mapping_found:
                        pmap = pd.read_csv(participant_mapping, dtype=str)
                        subject = pmap.loc[pmap[old_subj_id] == subject, new_subj_id].values[0].zfill(3)
                        
                        session = pmap.loc[pmap[old_session] == date_session, new_session].values[0].zfill(2)
                    
                    info = mne.io.read_raw_fif(full_file_name,
                                    allow_maxshield=True,
                                    verbose='error')
                    ch_types = set(info.get_channel_types())

                    if 'mag' in ch_types:
                        datatype = 'meg'
                        extension = '.fif'
                    elif 'eeg' in ch_types:
                        datatype = 'eeg'

                    bids_path = BIDSPath(
                        subject=subject,
                        session=session,
                        task=task,
                        acquisition=mod,
                        processing=None if proc == '' else proc,
                        run=None if run == '' else run,
                        datatype=datatype,
                        root=path_BIDS
                    )
                    
                    # Check if bids exist
                    run_conversion = 'yes'
                    if (find_matching_paths(bids_path.directory,
                                        tasks=task,
                                        acquisitions=mod,
                                        extensions='.fif')):
                        run_conversion = 'no'

                    processing_schema['time_stamp'].append(ts)
                    processing_schema['run_conversion'].append(run_conversion)
                    processing_schema['participant_from'].append(participant)
                    processing_schema['participant_to'].append(subject)
                    processing_schema['session_from'].append(date_session)
                    processing_schema['session_to'].append(session)
                    processing_schema['task'].append(task)
                    processing_schema['split'].append(split)
                    processing_schema['run'].append(run)
                    processing_schema['datatype'].append(datatype)
                    processing_schema['acquisition'].append(mod)
                    processing_schema['processing'].append(proc)
                    processing_schema['raw_path'].append(dirname(full_file_name))
                    processing_schema['raw_name'].append(file)
                    processing_schema['bids_path'].append(bids_path.directory)
                    
                    processing_schema['bids_name'].append(bids_path.basename)
                    

    df = pd.DataFrame(processing_schema)
    
    df.insert(2, 'task_count',
              df.groupby(['participant_to', 'acquisition', 'datatype', 'split', 'task', 'processing'])['task'].transform('count'))
    
    df.insert(3, 'task_flag', df.apply(
                lambda x: 'check' if x['task_count'] != df['task_count'].max() else 'ok', axis=1))
    

    os.makedirs(f'{path_BIDS}/conversion_logs', exist_ok=True)
    df.to_csv(f'{path_BIDS}/conversion_logs/{ts}_bids_conversion.tsv', sep='\t', index=False)

def load_conversion_table(config_dict: dict,
                          conversion_file: str=None):
        # Load the most recent conversion table
    path_BIDS = config_dict.get('BIDS')
    conversion_logs_path = os.path.join(path_BIDS, 'conversion_logs')
    if not os.path.exists(conversion_logs_path):
        print("No conversion logs directory found.")
        return None
        
    if not conversion_file:
        print(f"Loading most recent conversion table from {conversion_logs_path}")
        conversion_files = sorted(glob(os.path.join(conversion_logs_path, '*_bids_conversion.tsv')))
        if not conversion_files:
            print("Creating new conversion table")
            generate_new_conversion_table(config_dict)
            
        conversion_files = sorted(glob(os.path.join(conversion_logs_path, '*_bids_conversion.tsv')))

        latest_conversion_file = conversion_files[-1]
        print(f"Loading the most recent conversion table: {basename(latest_conversion_file)}")
        conversion_table = pd.read_csv(latest_conversion_file, sep='\t', dtype=str)
    else: 
        conversion_table = pd.read_csv(conversion_file, sep='\t', dtype=str)
        
    return conversion_table

def bidsify(config_dict: dict, conversion_file: str=None):
    
    path_BIDS = config_dict.get('BIDS')
    calibration = config_dict['Calibration']
    crosstalk = config_dict['Crosstalk']
    overwrite = config_dict['Overwrite']

    df = load_conversion_table(config_dict, conversion_file)
    df = df.where(pd.notnull(df), None)
    
    # Start by creating the BIDS directory structure
    unique_participants_sessions = df[['participant_to', 'session_to', 'datatype']].drop_duplicates()
    for _, row in unique_participants_sessions.iterrows():
        bids_path = BIDSPath(
            subject=row['participant_to'],
            session=row['session_to'],
            datatype=row['datatype'],
            root=path_BIDS
        ).mkdir()
        if row['datatype'] == 'meg':
            if not bids_path.meg_calibration_fpath:
                    write_meg_calibration(calibration, bids_path)
            if not bids_path.meg_crosstalk_fpath:
                write_meg_crosstalk(crosstalk, bids_path)
    
    # ignore split files as they are processed automatically
    df = df[df['split'].isna()]

    deviants = df[df['task_flag'] == 'check']
    if len(deviants) > 0:
        print('Deviants found:')
        print(deviants)
        print('Please check the conversion table')
        sys.exit(1)

    for i, d in df.iterrows():
        
        # Ignore files that are already converted
        if d['run_conversion'] == 'no' and overwrite == 'off':
            print(f"{d['bids_name']} already converted")
            continue

        raw_file = f"{d['raw_path']}/{d['raw_name']}"
        
        raw = mne.io.read_raw_fif(raw_file,
                                  allow_maxshield=True,
                                  verbose='error')

        ch_types = set(raw.info.get_channel_types())

        if 'mag' in ch_types:
            datatype = 'meg'
            extension = '.fif'
            suffix = 'meg'
        elif 'eeg' in ch_types:
            datatype = 'eeg'
            extension = None
            suffix = None
        
        subject = d['participant_to']
        session = d['session_to']
        task = d['task']
        acquisition = d['acquisition']
        processing = d['processing']
        run = d['run']

        # Create BIDS path
        bids_path = BIDSPath(
            subject=subject,
            session=session,
            task=task,
            run=run,
            datatype=datatype,
            acquisition=acquisition,
            processing=processing,
            suffix=suffix,
            extension=extension,
            root=path_BIDS
        )
        # Write the BIDS file
        try:
            write_raw_bids(
                raw=raw,
                bids_path=bids_path,
                empty_room=None,
                events=None,
                overwrite=True,
                verbose='error'
            )
        except Exception as e:
            print(f"Error writing BIDS file: {e}")
            # If write_raw_bids fails, try to save the raw file directly
            # Fall back on raw.save if write_raw_bids fails
            fname = bids_path.copy().update(suffix=datatype, extension = '.fif').fpath
            raw.save(fname, overwrite=True)
        
        # Copy EEG to MEG
        if datatype == 'eeg':
            copy_eeg_to_meg(raw_file, bids_path)
            
        # Update the sidecar file
        else:
            update_sidecar(bids_path)

        # Add channel parameters 
        if acquisition == 'hedscan':
            opm_tsv = f"{d['raw_path']}/{d['raw_name']}".replace('raw.fif', 'channels.tsv')
            
            bids_tsv = bids_path.copy().update(suffix='channels', extension='.tsv')
            add_channel_parameters(bids_tsv, opm_tsv)

        # Log the conversion
        log( 
            f'{raw_file} -> {bids_path}',
            level='info',
            logfile='log.tsv',
            logpath=path_BIDS
        )
        # Print the conversion
        print(f'{raw_file} -> {bids_path}')
        # Print the sidecar file
        print(f'{bids_path.fpath} updated')
        # Print the CapTrak file
        print(f'{bids_path.fpath} updated')
        
        df.at[i, 'run_conversion'] = 'no'
    
    # Update the conversion table
    df.to_csv(f'{path_BIDS}/conversion_logs/{df["time_stamp"].iloc[0]}_bids_conversion.tsv', sep='\t', index=False)

def main():
    parser = argparse.ArgumentParser(description='BIDSify Configuration')
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file')
    parser.add_argument('-e', '--edit', action='store_true', help='Launch the UI for configuration file')
    parser.add_argument('--conversion', type=str, help='Path to the conversion file')
    args = parser.parse_args()

    if args.config:
        file_config = args.config
    else:
        file_config = askForBidsConfig()
    # Select BIDS configuration file dialog
    
    if file_config == 'new':
        config_dict = openBidsConfigUI()
    elif file_config != 'new' and args.edit:
        config_dict = openBidsConfigUI(file_config)
    else:
        with open(file_config, 'r') as f:
            config_dict = json.load(f)

    if config_dict:
        for key, value in config_dict.items():
            print(f"{key}: {value}")
        
        # create dataset description file if the file does not exist or overwrite_bids is True

        create_dataset_description(config_dict['BIDS'], args.edit)
        
        bidsify(config_dict, args.conversion)
        
        update_sidecars(config_dict['BIDS'])

        print_dir_tree(config_dict['BIDS'])
    else:
        print('No configuration file selected')
        sys.exit(1)

if __name__ == "__main__":
    main()
