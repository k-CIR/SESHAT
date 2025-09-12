
import pandas as pd
import json
import yaml
import os
from shutil import copy2
from copy import deepcopy
from os.path import exists, basename, dirname, join
import sys
from glob import glob
import numpy as np
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess


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
from mne_bids.write import _sidecar_json
import mne
import time
from bids_validator import BIDSValidator
#from bids import BIDSLayout

from utils import (
    log, configure_logging,
    noise_patterns,
    headpos_patterns,
    askForConfig,
    extract_info_from_filename,
    file_contains,
    opm_exceptions_patterns
)
###############################################################################
# Variables
###############################################################################
exclude_patterns = [r'-\d+\.fif', '_trans', 'avg.fif']

###############################################################################
# Functions: Create or fill templates: dataset description, participants info
###############################################################################

def create_dataset_description(config: dict):
    """
    Create or update BIDS dataset_description.json file with metadata.
    
    Creates the BIDS root directory if it doesn't exist and generates a 
    dataset_description.json file with project metadata according to BIDS 
    specification.
    
    Args:
        config (dict): Configuration dictionary containing BIDS parameters
                      including dataset name, authors, funding, etc.
    
    Returns:
        None
    
    Side Effects:
        - Creates BIDS directory structure
        - Writes dataset_description.json file
        - Loads existing description data into memory
    """
    
    # Make sure the BIDS directory exists and create it if it doesn't
    os.makedirs(config['BIDS'], exist_ok=True)
    
    # Define the path to the dataset_description.json file
    
    file_bids = f"{config['BIDS']}/{config['Dataset_description']}"

    # Create empty dataset description if not exists
    if not exists(file_bids):
        make_dataset_description(
            path = config['BIDS'],
            name = config['name'],
            dataset_type = config['dataset_type'],
            data_license = config['data_license'],
            authors = config['authors'],
            acknowledgements = config['acknowledgements'],
            how_to_acknowledge = config['how_to_acknowledge'],
            funding = config['funding'],
            ethics_approvals = config['ethics_approvals'],
            references_and_links = config['references_and_links'],
            doi = config['doi'],
            overwrite = config['overwrite']
        )

def create_participants_files(config: dict):
    """
    Create BIDS participants.tsv and participants.json files with default structure.
    
    Generates template participant files with standard columns (participant_id, 
    sex, age, group) and corresponding JSON metadata file describing each field.
    
    Args:
        config (dict): Configuration dictionary with BIDS path and settings
    
    Returns:
        None
        
    Side Effects:
        - Creates participants.tsv with empty participant table
        - Creates participants.json with field descriptions
        - Prints creation messages
    """
    # check if participants.tsv and participants.json files is available or create a new one with default fields
    os.makedirs(config['BIDS'], exist_ok=True)
    
    tsv_file = os.path.join(config['BIDS'], config['Participants'])
    if not exists(tsv_file) or config['overwrite']:
        # create default fields participants.tsv
        participants = glob('sub*', root_dir=config['BIDS'])
        # create empty table with 4 columns (participant_id, sex, age)
        df = pd.DataFrame(columns=['participant_id', 'sex', 'age', 'group'])
            
        participants_tsv_path = os.path.join(config['BIDS'], 'participants.tsv')
        df.to_csv(participants_tsv_path, sep='\t', index=False)
        print(f"Writing {participants_tsv_path}")

    json_file = os.path.join(config['BIDS'], 'participants.json')

    if not exists(json_file) or config['overwrite']:
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

    participants_json_path = os.path.join(config['BIDS'], 'participants.json')
    with open(participants_json_path, 'w') as f:
            json.dump(participants_json, f, indent=4)
    print(f"Writing {participants_json_path}")

###############################################################################
# Help functions
###############################################################################

def get_parameters(config):
    """
    Extract and merge BIDS configuration parameters from file or dictionary.
    
    Reads configuration from JSON/YAML file or processes existing dictionary,
    combining project and BIDS-specific parameters into a unified configuration.
    
    Args:
        config (str or dict): Path to config file (.json/.yml/.yaml) or 
                             configuration dictionary
    
    Returns:
        dict: Merged configuration dictionary combining project and BIDS settings
        
    Raises:
        ValueError: If unsupported file format is provided
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
    
    bids_dict = deepcopy(config_dict['project']) | deepcopy(config_dict['bids'])
    return bids_dict

def update_sidecars(config: dict):
    """
    Update BIDS sidecar JSON files with institutional and acquisition metadata.
    
    Finds all MEG files in BIDS structure and updates their JSON sidecars with:
    - Institution information (name, department, address)
    - Associated empty room recordings
    - Head position and movement data
    - MaxFilter processing parameters
    - Dewar position and HPI coil frequencies
    
    Args:
        config (dict): Configuration dictionary with BIDS root path and 
                      institution details
    
    Returns:
        None
        
    Side Effects:
        - Modifies existing JSON sidecar files
        - Adds metadata fields to comply with BIDS specification
    """
    bids_root = config['BIDS']
    # Find all meg files in the BIDS folder, ignore EEG for now
    bids_paths = find_matching_paths(bids_root,
                                     suffixes='meg',
                                    acquisitions=['triux', 'hedscan'],
                                    splits=None,
                                    descriptions=None,
                                     extensions='.fif')
    # Add institution name, department and address
    institution = {
            'InstitutionName': config['InstitutionName'],
            'InstitutionDepartmentName': config['InstitutionDepartmentName'],
            'InstitutionAddress': config['InstitutionName']
            }
    
    for bp in bids_paths:
        if not file_contains(bp.basename, headpos_patterns):
            acq = bp.acquisition
            proc = bp.processing
            suffix = bp.suffix
            info = mne.io.read_info(bp.fpath, verbose='error')
            bp_json = bp.copy().update(extension='.json', split=None)
            # Check if json exists, if not create it
            if not exists(bp_json.fpath):
                raw = read_raw_bids(bp)
                _sidecar_json(raw=raw,
                              task=bp.task,
                              manufacturer='Elekta',
                              fname=bp_json.fpath,
                              datatype=bp.datatype)
            
            with open(str(bp_json.fpath), 'r') as f:
                sidecar = json.load(f)
            
            if not file_contains(bp.task.lower(), noise_patterns):
                match_paths = find_matching_paths(
                                bp.directory,
                                acquisitions=acq,
                                suffixes='meg',
                                extensions='.fif')

                noise_paths = [p for p in match_paths if 'noise' in p.task.lower()]
                sidecar['AssociatedEmptyRoom'] = [basename(er) for er in noise_paths]
                
                # Find associated headpos and trans files
                headpos_file = find_matching_paths(
                    bp.directory,
                    bp.task,
                    acquisitions=acq,
                    descriptions='headpos',
                    extensions='.pos',
                )
                trans_file = find_matching_paths(
                    bp.directory,
                    bp.task,
                    acquisitions=acq,
                    descriptions='trans',
                    extensions='.fif',
                )
                if headpos_file:
                    path = f"{headpos_file[0].root}/{headpos_file[0].basename}"
                    headpos = mne.chpi.read_head_pos(path)
                    trans_head, rot, t = mne.chpi.head_pos_to_trans_rot_t(headpos)
                    sidecar['MaxMovement'] = round(float(trans_head.max()), 4)
                    
                if trans_file:
                    path = f"{headpos_file[0].root}/{headpos_file[0].basename}"
                    trans = mne.read_trans(path)

            if acq == 'triux' and suffix == 'meg':
                if info['gantry_angle'] > 0:
                    dewar_pos = f'upright ({int(info["gantry_angle"])} degrees)'
                else:
                    dewar_pos = f'supine ({int(info["gantry_angle"])} degrees)'
                sidecar['DewarPosition'] = dewar_pos
                try:
                    # mne.chpi.get_chpi_info(info)
                    sidecar['HeadCoilFrequency'] = [f['coil_freq'] for f in info['hpi_meas'][0]['hpi_coils']]
                except IndexError:
                    'No head coil frequency found'

                # sidecar['ContinuousHeadLocalization']
                
                # TODO: Add maxfilter and headposition parameters
                if proc:
                    #print('Processing detected')
                    proc_list = proc.split('+')
                    max_info = info['proc_history'][0]['max_info']
                    
                    if file_contains(proc, ['sss', 'tsss']):
                        sss_info = max_info['sss_info']
                        sidecar['SoftwareFilters']['MaxFilterVersion'] = info['proc_history'][0]['creator']

                        sidecar['SoftwareFilters']['SignalSpaceSeparation'] = {
                            'Origin': sss_info['origin'].tolist(),
                            'NComponents': sss_info['nfree'],
                            
                        }

                        if any(['hpi' in key for key in sss_info.keys()]):
                            sidecar['SoftwareFilters']['SignalSpaceSeparation'][ 'HpiGoodLimit'] = sss_info['hpi_g_limit']
                            sidecar['SoftwareFilters']['SignalSpaceSeparation']['HPIDistanceLimit'] = sss_info['hpi_dist_limit']

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
            
            if not new_sidecar == sidecar:

                with open(str(bp_json.fpath), 'w') as f:
                    json.dump(new_sidecar, f, indent=4)

def add_channel_parameters(
    bids_tsv: str,
    opm_tsv: str):

    print(bids_tsv, opm_tsv)
    """
    Merge additional channel parameters from OPM source file into BIDS channels.tsv.
    
    Compares OPM-specific channel file with BIDS channels file and adds any
    missing columns or parameters to ensure complete channel documentation.
    
    Args:
        bids_tsv (str): Path to BIDS channels.tsv file
        omp_tsv (str): Path to source OPM channels.tsv with additional parameters
    
    Returns:
        None
        
    Side Effects:
        - Updates BIDS channels.tsv file with merged data
        - Prints confirmation message
    """
    if exists(opm_tsv):
        orig_df = pd.read_csv(opm_tsv, sep='\t')
        if not exists(bids_tsv):
            bids_df = orig_df.copy()
        else:
            bids_df = pd.read_csv(bids_tsv, sep='\t')

        # Compare file with file in BIDS folder

        add_cols = [c for c in orig_df.columns
                    if c not in bids_df.columns] + ['name']

        if not np.array_equal(
            orig_df, bids_df):
            
            bids_df = bids_df.merge(orig_df[add_cols], on='name', how='outer')

            bids_df.to_csv(bids_tsv, sep='\t', index=False)
    print(f'Adding channel parameters to {basename(bids_tsv)}')

def copy_eeg_to_meg(file_name: str, bids_path: BIDSPath):
    """
    Copy EEG data files to MEG datatype directory in BIDS structure.
    
    For files containing only EEG channels, copies the data and metadata
    to the MEG directory and includes associated CapTrak digitization files.
    
    Args:
        file_name (str): Path to source EEG file
        bids_path (BIDSPath): BIDS path object for target location
    
    Returns:
        None
        
    Side Effects:
        - Saves EEG data as MEG datatype
        - Copies JSON metadata files
        - Copies associated CapTrak digitization files
    """
    if not file_contains(file_name, headpos_patterns):
        raw = mne.io.read_raw_fif(file_name, allow_maxshield=True, verbose='error')
        ch_types = set(raw.info.get_channel_types())
        # Confirm that the file is EEG
        if not 'meg' in ch_types:
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

def generate_new_conversion_table(config: dict):
    
    """
    For each participant and session within MEG folder, move the files to BIDS correspondent folder
    or create a new one if the session does not match. Change the name of the files into BIDS format.
    """
    # TODO: parallelize the conversion
    ts = datetime.now().strftime('%Y%m%d')
    path_project = config['opmMEG'].replace('raw', '') or config['squidMEG'].replace('raw', '')
    path_triux = config['squidMEG']
    path_opm = config['opmMEG']
    path_BIDS = config['BIDS']
    participant_mapping = join(path_project,config['Participants_mapping_file'])
    old_subj_id = config['Original_subjID_name']
    new_subj_id = config['New_subjID_name']
    old_session = config['Original_session_name']
    new_session = config['New_session_name']
    tasks = config['tasks'] + opm_exceptions_patterns
    
    processing_modalities = []
    if path_triux != '' and str(path_triux) != '()':
        processing_modalities.append('triux')
    if path_opm != '' and str(path_opm) != '()':
        processing_modalities.append('hedscan')
    
    if participant_mapping:
        mapping_found=True
        try:
            pmap = pd.read_csv(participant_mapping, dtype=str)
        except FileExistsError as e:
            mapping_found=False
            print('Participant file not found, skipping')
    
    path = path_triux if 'triux' in processing_modalities else path_opm
    participants = glob('sub-*', root_dir=path)

    def process_file_entry(args):
        participant, date_session, mod, file = args
        full_file_name = os.path.join(path, participant, date_session, mod, file)
        
        info_dict = {}
        if exists(full_file_name):
            info_dict = extract_info_from_filename(full_file_name)
        task = info_dict.get('task')
        proc = '+'.join(info_dict.get('processing'))
        datatypes = '+'.join([d for d in info_dict.get('datatypes') if d != ''])
        subject = info_dict.get('participant')
        split = info_dict.get('split')
        run = ''
        desc = '+'.join(info_dict.get('description'))
        extension = info_dict.get('extension')
        suffix = 'meg'
        event_file = glob(f'{task}_event_id.json', root_dir=f'{path_BIDS}/..')
        if event_file:
            event_file = event_file[0]
        else:
            event_file = None

        process_file = True
        subj_out = subject
        session_out = date_session

        if participant_mapping and mapping_found:
            check_subj = subject in pmap[old_subj_id].values
            check_date = date_session in pmap.loc[pmap[old_subj_id] == subject, old_session].values
            process_file = all([check_subj, check_date])
            if process_file:
                subj_out = pmap.loc[pmap[old_subj_id] == subject, new_subj_id].values[0].zfill(3)
                session_out = pmap.loc[pmap[old_session] == date_session, new_session].values[0].zfill(2)

        if process_file and not file_contains(file, headpos_patterns):
            try:
                info = mne.io.read_raw_fif(full_file_name, allow_maxshield=True, verbose='error')
                ch_types = set(info.get_channel_types())
            except Exception as e:
                print(f"Error reading file {full_file_name}: {e}")
                ch_types = ['']
            if 'mag' in ch_types:
                datatype = 'meg'
            elif 'eeg' in ch_types:
                datatype = 'eeg'
                extension = None
                suffix = 'eeg'
            else:
                datatype = 'meg'
                extension = None
                suffix = None
        else:
            datatype = 'meg'

        if process_file:
            try:
                bids_path = BIDSPath(
                    subject=subj_out,
                    session=session_out,
                    task=task,
                    acquisition=mod,
                    processing=None if proc == '' else proc,
                    run=None if run == '' else run,
                    datatype=datatype,
                    description=None if desc == '' else desc,
                    root=path_BIDS,
                    extension=extension,
                    suffix=suffix
                )
            except ValueError as e:
                print(f"Error creating BIDSPath for {full_file_name}: {e}")
                return None

            # Check if bids exist
            run_conversion = 'yes'
            if (find_matching_paths(bids_path.directory,
                                   tasks=task,
                                   acquisitions=mod,
                                   suffixes=suffix,
                                   descriptions=None if desc == '' else desc,
                                   extensions=extension)):
                run_conversion = 'no'

            return {
                'time_stamp': ts,
                'run_conversion': run_conversion,
                'participant_from': participant,
                'participant_to': subj_out,
                'session_from': date_session,
                'session_to': session_out,
                'task': task,
                'split': split,
                'run': run,
                'datatype': datatype,
                'acquisition': mod,
                'processing': proc,
                'description': desc,
                'raw_path': dirname(full_file_name),
                'raw_name': file,
                'bids_path': bids_path.directory,
                'bids_name': bids_path.basename,
                'event_id': event_file
            }
        return None

    # Prepare all jobs
    jobs = []
    for participant in participants:
        sessions = sorted([session for session in glob('*', root_dir=os.path.join(path, participant)) if os.path.isdir(os.path.join(path, participant, session))])
        for date_session in sessions:
            for mod in processing_modalities:
                all_files = sorted(glob('*.fif', root_dir=os.path.join(path, participant, date_session, mod)) +
                                   glob('*.pos', root_dir=os.path.join(path, participant, date_session, mod)))
                for file in all_files:
                    jobs.append((participant, date_session, mod, file))

    results = []
    with ThreadPoolExecutor() as executor:
        future_to_job = {executor.submit(process_file_entry, job): job for job in jobs}
        for future in as_completed(future_to_job):
            res = future.result()
            if res is not None:
                results.append(res)

    df = pd.DataFrame(results)

    if not df.empty:
        df.insert(2, 'task_flag', df.apply(
            lambda x: 'check' if x['task'] not in tasks + ['Noise'] else 'ok', axis=1))
            # Added Noise to accepted task patterns
    else:
        df = pd.DataFrame(columns=[
            'time_stamp', 'run_conversion', 'participant_from', 'participant_to',
            'session_from', 'session_to', 'task', 'split', 'run', 'datatype',
            'acquisition', 'processing', 'description', 'raw_path', 'raw_name',
            'bids_path', 'bids_name', 'event_id', 'task_flag'
        ])

    os.makedirs(f'{path_BIDS}/conversion_logs', exist_ok=True)
    df.to_csv(f'{path_BIDS}/conversion_logs/bids_conversion.tsv', sep='\t', index=False)
    return df

# TODO: continue check here


def load_conversion_table(config: dict):
    """
    Load or generate conversion table for BIDS conversion process.
    
    Loads the most recent conversion table from logs directory, or generates
    a new one if none exists or if overwrite is requested.
    
    Args:
        config (dict): Configuration dictionary with BIDS path
        conversion_file (str, optional): Specific conversion file to load
        overwrite (bool): Force regeneration of conversion table
    
    Returns:
        pd.DataFrame: Conversion table with file mappings and metadata
        
    Side Effects:
        - Creates conversion_logs directory if missing
        - May generate new conversion table
        - Prints table loading information
    """
        # Load the most recent conversion table
    path_BIDS = config['BIDS']
    conversion_file = config['Conversion_file']
    overwrite = config['Overwrite_conversion']
    
    conversion_logs_path = os.path.join(path_BIDS, 'conversion_logs')
    if not os.path.exists(conversion_logs_path):
        os.makedirs(conversion_logs_path, exist_ok=True)
        print("No conversion logs directory found. Created new")
    
    if conversion_file:
        conversion_file = os.path.join(conversion_logs_path, conversion_file)
    
    if exists(conversion_file) and not overwrite:
        print(f"Loading conversion table from {conversion_file}")
        conversion_table = pd.read_csv(conversion_file, sep='\t', dtype=str)
        return conversion_table, conversion_file
    else:
        if overwrite:
            print(f'Overwrite requested, generating new conversion table')
        else:
            print(f'Conversion file {conversion_file} not found, generating new')
        
        generate_new_conversion_table(config)
        conversion_file_path = f'{path_BIDS}/conversion_logs/bids_conversion.tsv'
        while not exists(conversion_file_path):
            time.sleep(0.5)
        # After generation, load the newly created file
        conversion_files = sorted(
            glob(os.path.join(conversion_logs_path, '*.tsv')),
            key=os.path.getctime
        )
        print(f"Found conversion files: {conversion_files}")
        if conversion_files:
            latest_conversion_file = conversion_files[-1]
            print(f"Loading the most recent conversion table: {basename(latest_conversion_file)}")
            conversion_table = pd.read_csv(latest_conversion_file, sep='\t', dtype=str)
            return conversion_table, latest_conversion_file
        else:
            raise FileNotFoundError("No conversion files found after generation")

def update_conversion_table(conversion_table: pd.DataFrame, 
                            conversion_file: str=None):
    """
    Update conversion table to reflect current BIDS directory state.
    
    Checks which files have already been converted by examining the BIDS
    directory and updates the 'run_conversion' flag accordingly.
    
    Args:
        conversion_table (pd.DataFrame): Current conversion table
        conversion_file (str, optional): Path to save updated table
    
    Returns:
        pd.DataFrame: Updated conversion table with current conversion status
        
    Side Effects:
        - Modifies conversion table in place
        - Saves updated table to file if path provided
        - Prints conversion status updates
    """
    ts = datetime.now().strftime('%Y%m%d')
    
    conversion_table = conversion_table.where(pd.notnull(conversion_table), None)
    for i, row in conversion_table.iterrows():
        
        # Check if raw file has already been converted
        raw_file = f"{row['raw_path']}/{row['raw_name']}"
        
        files = (glob(row['bids_name'] + '*',
                 root_dir=row['bids_path']) + 
            glob(row['bids_name'].rsplit('_', 1)[0] + '_split*' + row['bids_name'].rsplit('_', 1)[1] + '*', 
                 root_dir=row['bids_path'])) 
    
        if not files:
            conversion_table.at[i, 'run_conversion'] = 'yes'
            conversion_table.at[i, 'time_stamp'] = ts
        
        # TODO: Add argument for update if file exists
    
    conversion_table.to_csv(f'{conversion_file}', sep='\t', index=False)
    return conversion_table

        
def bidsify(config: dict):
    """
    Main function to convert raw MEG/EEG data to BIDS format.
    
    Comprehensive conversion process that:
    1. Loads/updates conversion table
    2. Creates BIDS directory structure
    3. Processes each file according to conversion table
    4. Handles MEG, EEG, head position, and transformation files
    5. Associates event files with task data
    6. Manages calibration and crosstalk files
    7. Logs all conversion activities
    
    Conversion Features:
    - Supports both TRIUX (SQUID) and OPM MEG systems
    - Handles split files automatically
    - Zero-pads subject and session IDs
    - Associates event files with tasks
    - Copies head position and transformation files
    - Manages channel parameter files for OPM data
    - Robust error handling with fallback options
    
    Args:
        config (dict): Complete configuration with paths and parameters
        conversion_file (str, optional): Specific conversion table to use
        overwrite (bool): Whether to overwrite existing BIDS files
    
    Returns:
        None
        
    Side Effects:
        - Creates complete BIDS directory structure
        - Converts all eligible raw files to BIDS format
        - Writes calibration and crosstalk files
        - Updates conversion table with completion status
        - Logs all conversion activities
        
    Raises:
        SystemExit: If task validation fails (unknown tasks found)
    """
    
    # TODO: parallelize the conversion
    ts = datetime.now().strftime('%Y%m%d')
    local_path = config['squidMEG'] if config['squidMEG'] != '' else config['opmMEG']
    path_BIDS = config['BIDS']
    calibration = f"{local_path}/{config['Calibration']}"
    crosstalk = f"{local_path}/{config['Crosstalk']}"
    crosstalk = config['Crosstalk']
    overwrite = config['overwrite']
    logfile = config['Logfile']
    logpath = config['BIDS'].replace('raw', 'log')

    configure_logging(log_dir=logpath, log_file=logfile)
    # overwrite = config['Overwrite']

    df, conversion_file = load_conversion_table(config)
    #df = update_conversion_table(df, conversion_file)
    df = df.where(pd.notnull(df), None)

    df['participant_to'] = df['participant_to'].str.zfill(3)
    
    # Start by creating the BIDS directory structure
    unique_participants_sessions = df[['participant_to', 'session_to', 'datatype']].drop_duplicates()
    for _, row in unique_participants_sessions.iterrows():
        subject_padded = str(row['participant_to']).zfill(3)
        session_padded = str(row['session_to']).zfill(2)
        bids_path = BIDSPath(
            subject=subject_padded,
            session=session_padded,
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

    # Flag deviants and exist if found
    deviants = df[df['task_flag'] == 'check']
    if len(deviants) > 0:
        log('BIDS', 'Deviants found, please check the conversion table and run again', level='warning', logfile=logfile, logpath=logpath)
        return

    for i, d in df.iterrows():
        
        # Ignore files that are already converted
        if d['run_conversion'] == 'no' and not overwrite:
            #print(f"{d['bids_name']} already converted")
            continue
        
        raw_file = f"{d['raw_path']}/{d['raw_name']}"
        if not file_contains(raw_file, headpos_patterns):
            try:
                raw = mne.io.read_raw_fif(raw_file,
                                        allow_maxshield=True,
                                        verbose='error')
            except Exception as e:
                log('BIDS', f'Error reading {raw_file}: {e}', level='error', logfile=logfile, logpath=logpath)
                continue

            ch_types = set(raw.info.get_channel_types())
            

            if 'mag' in ch_types:
                datatype = 'meg'
                extension = '.fif'
                suffix = 'meg'
            elif 'eeg' in ch_types:
                datatype = 'eeg'
                extension = None
                suffix = None
            elif raw_file.endswith('.fif'):
                datatype = 'meg'
                extension = '.fif'
                suffix = 'meg'

            # Added leading zero-padding to subject and session
            if len(d['participant_to']) > 3:
                subject = str(d['participant_to']).zfill(3)
            else:
                subject = str(d['participant_to']).zfill(3)
            
            session = str(d['session_to']).zfill(2)
            task = d['task']
            acquisition = d['acquisition']
            processing = d['processing']
            run = d['run']
            event_id = d['event_id']
            
            if event_id:
                with open(f"{path_BIDS}/../{event_id}", 'r') as f:
                    event_id = json.load(f)
                events = mne.find_events(raw)
                
            else:
                event_id = None
                events = None
            

            # Create BIDS path
            bids_path = BIDSPath(
                subject=subject,
                session=session,
                task=task,
                run=None if run == '' else run,
                datatype=datatype,
                acquisition=acquisition,
                processing=None if processing == '' else processing,
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
                    event_id=event_id,
                    events=events,
                    overwrite=True,
                    verbose='error'
                )
            except Exception as e:
                print(f"Error writing BIDS file: {e}")
                # If write_raw_bids fails, try to save the raw file directly
                # Fall back on raw.save if write_raw_bids fails
                fname = bids_path.copy().update(suffix=datatype, extension = '.fif').fpath
                try:
                    raw.save(fname, overwrite=True)
                except Exception as e:
                    print(f"Error saving raw file: {e}")
                    log('BIDS',
                        f'{fname} not bidsified',
                        level='error',
                        logfile=logfile,
                        logpath=logpath
                        )

            # Copy EEG to MEG
            if datatype == 'eeg':
                copy_eeg_to_meg(raw_file, bids_path)

            # Add channel parameters 
            if acquisition == 'hedscan' and not processing:
                
                opm_tsv = f"{d['raw_path']}/{d['raw_name']}".replace('raw.fif', 'channels.tsv')
                
                bids_tsv = bids_path.copy().update(suffix='channels', extension='.tsv')
                add_channel_parameters(bids_tsv, opm_tsv)


        # If the file is a head position file, copy it to the BIDS directory
        # and rename it to the BIDS format
        else:
            bids_path = f"{d['bids_path']}/{d['bids_name']}"

            if 'headpos' in d['description']:
                headpos = mne.chpi.read_head_pos(raw_file)
                mne.chpi.write_head_pos(bids_path, headpos)
            elif 'trans' in d['description']:
                trans = mne.read_trans(raw_file)
                mne.write_trans(bids_path, trans, overwrite=True)

        # Log and print the conversion
        log('BIDS',
            f'{raw_file} -> {bids_path}',
            level='info',
            logfile=logfile,
            logpath=logpath
        )
        
        # Update the conversion table
        df.at[i, 'time_stamp'] = ts
        df.at[i, 'run_conversion'] = 'no'
        df.at[i, 'run_conversion'] = 'no'
        df.at[i, 'bids_path'] = dirname(bids_path)
        df.at[i, 'bids_name'] = basename(bids_path)

    # Save updated conversion table
    update_conversion_table(df, conversion_file)
    log('BIDS', f'All files bidsified according to {conversion_file}', level='info', logfile=logfile, logpath=logpath)
    # df.to_csv(f'{path_BIDS}/conversion_logs/bids_conversion.tsv', sep='\t', index=False)
    

def args_parser():
    """
    Parse command-line arguments for bidsify script.
    
    Defines command-line interface for standalone script execution with
    options for configuration file, conversion table, and overwrite settings.
    
    Returns:
        argparse.Namespace: Parsed command-line arguments
    """
    parser = argparse.ArgumentParser(description=
                                     '''
BIDS Conversion Pipeline
This script runs the complete BIDS conversion pipeline for MEG/EEG data.
It includes:
- Loading configuration from file or command-line
- Creating dataset description
- Running BIDS conversion process
- Updating JSON sidecars with metadata
- Displaying final BIDS directory tree                  
                                     ''',
                                     add_help=True)
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    args = parser.parse_args()
    return args


def validate_bids(config: dict):
    """
    Validate BIDS directory structure and contents using bids-validator.
    
    Args:
        config (dict): Configuration dictionary with BIDS path
    
    Returns:
        bool: True if validation passes, False otherwise
    """
    
    bids_root = config['BIDS']
    logfile = config.get('Logfile', 'bidsify.log')
    logpath = config.get('BIDS', '').replace('raw', 'log')
    
    if not os.path.exists(bids_root):
        log('BIDS', f"BIDS directory {bids_root} does not exist", level='error', logfile=logfile, logpath=logpath)
        return False
    
    try:
        # Run bids-validator
        result = subprocess.run(
            ['bids-validator', bids_root, '--json'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            log('BIDS', 'BIDS validation passed', level='info', logfile=logfile, logpath=logpath)
            return True
        else:
            # Parse JSON output for detailed errors
            try:
                validation_result = json.loads(result.stdout)
                errors = validation_result.get('issues', {}).get('errors', [])
                warnings = validation_result.get('issues', {}).get('warnings', [])
                
                for error in errors:
                    log('BIDS', f"Validation error: {error.get('reason', 'Unknown error')}", 
                        level='error', logfile=logfile, logpath=logpath)
                
                for warning in warnings:
                    log('BIDS', f"Validation warning: {warning.get('reason', 'Unknown warning')}", 
                        level='warning', logfile=logfile, logpath=logpath)
                        
            except json.JSONDecodeError:
                # Fallback to plain text output
                log('BIDS', f"Validation failed: {result.stderr}", level='error', logfile=logfile, logpath=logpath)
            
            return False
            
    except subprocess.TimeoutExpired:
        log('BIDS', 'BIDS validation timed out', level='error', logfile=logfile, logpath=logpath)
        return False
    except FileNotFoundError:
        log('BIDS', 'bids-validator not found. Install with: npm install -g bids-validator', 
            level='error', logfile=logfile, logpath=logpath)
        return False
    except Exception as e:
        log('BIDS', f"Validation error: {str(e)}", level='error', logfile=logfile, logpath=logpath)
        return False

def main(config:str=None):
    """
    Main entry point for BIDS conversion pipeline.
    
    Orchestrates the complete BIDS conversion process:
    1. Loads configuration (from file or parameter)
    2. Creates dataset description
    3. Runs main bidsification process
    4. Updates JSON sidecars with metadata
    5. Displays final BIDS directory tree
    
    Args:
        config (dict, optional): Configuration dictionary. If None, loads from
                                command-line arguments or user selection.
    
    Returns:
        None
        
    Side Effects:
        - Executes complete BIDS conversion pipeline
        - Prints directory tree of final BIDS structure
        
    Raises:
        SystemExit: If no configuration file is provided
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
    
    if isinstance(config, str):
        # If config is a string, assume it's a path to a config file
        config = get_parameters(config)
    
    create_dataset_description(config)
    bidsify(config)
    update_sidecars(config)
    print_dir_tree(config['BIDS'])
    return True
    

if __name__ == "__main__":
    main()
