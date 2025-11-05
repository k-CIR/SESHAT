
import pandas as pd
import json
import yaml
import os
from shutil import copy2
import re
from copy import deepcopy
from os.path import exists, basename, dirname, join, getsize
import sys
from glob import glob
import numpy as np
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
from tqdm import tqdm


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
from copy_to_cerberos import get_split_file_parts
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

# Conversion table field descriptions for user guidance
CONVERSION_TABLE_FIELDS = {
    'time_stamp': 'Date when entry was created (YYYYMMDD)',
    'status': 'Processing status: check=needs review, run=ready to convert, processed=converted, skip=ignore',
    'participant_from': 'Original participant identifier from filename',
    'participant_to': 'Target BIDS participant ID (zero-padded)',
    'session_from': 'Original session identifier from filename', 
    'session_to': 'Target BIDS session ID (zero-padded)',
    'task': 'BIDS task name (EDITABLE - main field for manual changes)',
    'acquisition': 'MEG acquisition type (triux/hedscan)',
    'processing': 'Processing pipeline applied (hpi, sss, etc.)',
    'description': 'Additional BIDS description field',
    'datatype': 'BIDS datatype (meg/eeg)', 
    'split': 'Split file indicator for large files',
    'run': 'BIDS run number for repeated acquisitions',
    'raw_path': 'Full path to source raw file directory',
    'raw_name': 'Source raw filename',
    'bids_path': 'Target BIDS directory path', 
    'bids_name': 'Target BIDS filename',
    'event_id': 'Associated event file for task'
}

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
            name = config['Name'],
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

def create_proc_description(config: dict):
    
    bids_root = config['BIDS']
    proc_root = config['BIDS'] + '/derivatives/preprocessed'    
    os.makedirs(proc_root, exist_ok=True)
    
    proc_mapping = {
        'sss': 'Signal Space Separation (SSS) applied',
        'hpi': 'Digitized head position and HPI coils added',
        'ds': 'Downsampled data',
        'mc': 'Head motion correction applied',
        'avgHead': 'Data aligned to average head position',
        'corr': 'Correlation treashold applied',
        'tsss': 'Temporal Signal Space Separation (tSSS) applied',
    }
    df = pd.DataFrame(list(proc_mapping.items()), columns=['desc_id', 'description'])
    df.to_csv(join(proc_root, 'descriptions.tsv'), sep='\t', index=False)


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
    
    bids_dict = deepcopy(config_dict['Project']) | deepcopy(config_dict['BIDS'])
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
    proc_root = join(bids_root, 'derivatives', 'preprocessed')
    # Find all meg files in the BIDS folder, ignore EEG for now
    bids_paths = find_matching_paths(bids_root,
                                     suffixes='meg',
                                    acquisitions=['triux', 'hedscan'],
                                    splits=None,
                                    descriptions=None,
                                     extensions='.fif',
                                     ignore_nosub=True)
    proc_bids_paths = find_matching_paths(proc_root,
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
    
    for bp in bids_paths + proc_bids_paths:
        if not file_contains(bp.basename, headpos_patterns + ['trans']):
            acq = bp.acquisition
            suffix = bp.suffix
            proc = bp.processing
            try:
                info = mne.io.read_info(bp.fpath, verbose='error')
            except Exception as e:
                print(bp.fpath, e)
                continue
            bp_json = bp.copy().update(extension='.json', split=None)
            # Check if json exists, if not create it
            if not exists(bp_json.fpath):
                raw = read_raw_bids(bp, verbose='error')
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
                    trans = mne.read_trans(path, verbose='error')

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
                if info['proc_history']:
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
    
    if not file_contains(file_name, headpos_patterns + ['trans']):
        bids_path.update(extension='.vhdr')
        raw = read_raw_bids(bids_path, verbose='error')
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

###############################################################################
# Functions: Conversion Table Management
###############################################################################


def bids_path_from_filename(file_name, date_session, config, pmap=None):
    """
    Extract BIDS path from filename using config and optional participant mapping.
    
    Args:
        file_path: Path to the raw file
        date_session: Session identifier
        mod: Modality (triux/hedscan)
        config: Configuration dictionary containing all paths and settings
        pmap: Optional participant mapping dataframe
    
    Returns:
        BIDSPath object or None if extraction fails
    """
    # Extract info from filename
    if not exists(file_name):
        print(f"Not exists: {file_name}")
        return None
    
    bids_root = config.get('BIDS', '')
    info_dict = extract_info_from_filename(file_name)
    
    # Validate required fields
    task = info_dict.get('task')
    subject = info_dict.get('participant')
    if not task or not subject:
        print(f"Missing required fields in {file_name}")
        return None
    
    acquisition = basename(os.path.dirname(file_name))
    
    # Check if preprocessed and add derivatives path if so
    proc = '+'.join(info_dict.get('processing', []))
    if proc:
        bids_root = join(bids_root, 'derivatives', 'preprocessed')
    
    # Build processing info
    split = info_dict.get('split')
    run = info_dict.get('run', '')
    desc = info_dict.get('description')
    extension = info_dict.get('extension')
    suffix = info_dict.get('suffix')
    
    # Map participant/session if needed
    subj_out = subject.zfill(4)
    session_out = date_session

    if pmap is not None:
        old_subj_id = config.get('Original_subjID_name', '')
        new_subj_id = config.get('New_subjID_name', '')
        old_session = config.get('Original_session_name', '')
        new_session = config.get('New_session_name', '')
        
        check_subj = subject in pmap[old_subj_id].values
        check_date = date_session in pmap.loc[pmap[old_subj_id] == subject, old_session].values
        
        if not all([check_subj, check_date]):
            print('Not mapped participant/session')
            return None  # Skip unmapped participants/sessions
            
        subj_out = pmap.loc[pmap[old_subj_id] == subject, new_subj_id].values[0].zfill(3)
        session_out = pmap.loc[pmap[old_session] == date_session, new_session].values[0].zfill(2)

    # Determine datatype by reading file (only if not headpos/trans)
    datatype = 'meg' # Default
    if not file_contains(basename(file_name), headpos_patterns + ['trans']):
        try:
            info = mne.io.read_info(file_name, verbose='error')
            ch_types = set(info.get_channel_types())
            
            if 'mag' in ch_types:
                datatype = 'meg'
                extension = '.fif'
            elif 'eeg' in ch_types:
                datatype = 'eeg'
                extension = ''
                suffix = 'eeg'
        except Exception as e:
            print(f"Error reading file {file_name}: {e}")
            ch_types = ['']

    try:
        bids_path = BIDSPath(
            root=bids_root,
            subject=subj_out,
            session=session_out,
            task=task,
            acquisition=acquisition,
            processing=None if proc == '' else proc,
            run=None if run == '' else run.zfill(2),
            datatype=datatype,
            description=None if desc == '' else desc,
            extension=None if extension == '' else extension,
            suffix=None if suffix == '' else suffix
        )
    except ValueError as e:
        print(f"Error creating BIDSPath for {file_name}: {e}")
        return None
    
    return bids_path, info_dict


def generate_new_conversion_table(config: dict):
    
    """
    For each participant and session within MEG folder, generate conversion table entries.
    Uses parallel processing for efficiency.
    """
    ts = datetime.now().strftime('%Y%m%d')
    path_project = join(config.get('Root', ''), config.get('Name', ''))
    path_raw = config.get('Raw', '')
    path_BIDS = config.get('BIDS', '')
    participant_mapping = join(path_project, config.get('Participants_mapping_file', ''))
    old_subj_id = config.get('Original_subjID_name', '')
    new_subj_id = config.get('New_subjID_name', '')
    old_session = config.get('Original_session_name', '')
    new_session = config.get('New_session_name', '')
    tasks = config.get('Tasks', []) + opm_exceptions_patterns
    
    processing_modalities = ['triux', 'hedscan']
    
    # Load participant mapping if available
    pmap = None
    if participant_mapping:
        try:
            pmap = pd.read_csv(participant_mapping, dtype=str)
        except Exception as e:
            print('Participant mapping file not found, skipping')
    
    participants = glob('sub-*', root_dir=path_raw)
    
    def process_file_entry(job):
        """Process a single file entry - designed for parallel execution"""
        participant, date_session, mod, file = job
        full_file_name = os.path.join(path_raw, participant, date_session, mod, file)
        
        bids_path, info_dict = bids_path_from_filename(full_file_name, date_session, config, pmap)
        split = info_dict.get('split')
        
        if not bids_path:
            return None
        
        # Extract values from bids_path object
        task = bids_path.task
        run = bids_path.run
        datatype = bids_path.datatype
        proc = bids_path.processing
        desc = bids_path.description
        suffix = bids_path.suffix
        extension = bids_path.extension
        subj_out = bids_path.subject
        session_out = bids_path.session
        bids_path.acquisition
        
        # Check for event file
        event_file = None
        if task:
            event_files = glob(f'{task}_event_id.json', root_dir=f'{path_BIDS}/..')
            if event_files:
                event_file = event_files[0]
        
        # Check if BIDS file already exists
        if (find_matching_paths(bids_path.directory,
                                tasks=task,
                                acquisitions=mod,
                                suffixes=None if suffix == '' else suffix, 
                                descriptions=None if desc == '' else desc,
                                extensions=None if extension == '' else extension)):
            status = 'processed'
        else:
            status = 'run'

        if task not in tasks + ['Noise']:
            status = 'check'

        return {
            'time_stamp': ts,
            'status': status,
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
    
    # Collect all jobs
    jobs = []
    for participant in participants:
        sessions = sorted([session for session in glob('*', root_dir=os.path.join(path_raw, participant)) 
                          if os.path.isdir(os.path.join(path_raw, participant, session))])
        for date_session in sessions:
            for mod in processing_modalities:
                all_files = sorted(glob('*.fif', root_dir=os.path.join(path_raw, participant, date_session, mod)) +
                                   glob('*.pos', root_dir=os.path.join(path_raw, participant, date_session, mod)))
                for file in all_files:
                    jobs.append((participant, date_session, mod, file))
    
    # Process jobs in parallel and yield results as they complete
    max_workers = min(4, os.cpu_count() or 1)  # Use up to 4 workers
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_file_entry, job): job for job in jobs}
        
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    yield result
            except Exception as e:
                job = futures[future]
                print(f"Error processing {job}: {e}")
                continue

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
        
        results = list(generate_new_conversion_table(config))
        conversion_table = pd.DataFrame(results)

        conversion_file_path = f'{path_BIDS}/conversion_logs/bids_conversion.tsv'
        conversion_table.to_csv(conversion_file_path, sep='\t', index=False)
        print(f"New conversion table generated and saved to {basename(conversion_file_path)}")
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

def update_conversion_table(config, conversion_file=None) -> pd.DataFrame:
    """
    Update conversion table to add new files not currently tracked.
    
    Args:
        config (dict): Configuration dictionary with BIDS path and settings
    
    Returns:
        pd.DataFrame: Updated conversion table with new files added
        
    Side Effects:
        - Adds new entries for discovered files
        - Set status of new files to 'run' or 'check'
    """
    existing_conversion_table, existing_conversion_file = load_conversion_table(config)
    
    if not conversion_file:
        conversion_file = existing_conversion_file
    
    results = list(generate_new_conversion_table(config))
    new_conversion_table = pd.DataFrame(results)
    
    # ignore split
    new_conversion_table = new_conversion_table[new_conversion_table['split'].isna() | 
                                                (new_conversion_table['split'] == '')]
    
    # Double check if bids_file exists:
    for _, row in existing_conversion_table.iterrows():
        bids_files = (glob(row['bids_name'] + '*',
                 root_dir=row['bids_path']) + 
            glob(row['bids_name'].rsplit('_', 1)[0] + '_split*' + row['bids_name'].rsplit('_', 1)[1], 
                 root_dir=row['bids_path']))
        if not bids_files:
            row['status'] = 'run'
    
    # Extract files not in existing conversion table
    diff = pd.concat([existing_conversion_table, new_conversion_table]).drop_duplicates(
        subset=['raw_path', 'raw_name'],
        keep=False,
    ).reset_index(drop=True)
    
    if len(diff) == 0:
        print("No new files to add to conversion table.")
        return existing_conversion_table, conversion_file
    
    else:
        # Always set status to 'run' for new files
        if 'status' in diff.columns:
            diff.loc[diff['status'].isin(['processed', 'skip']), 'status'] = 'run'
        
        updated_table = pd.concat([existing_conversion_table, diff], ignore_index=True)  
        print(f"Adding {len(diff)} new files to conversion table.")
        
        return updated_table, conversion_file

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
    path_project = join(config.get('Root', ''), config.get('Name', ''))
    local_path = config.get('Raw', '')
    path_BIDS = config.get('BIDS', '')
    calibration = config.get('Calibration', '')
    crosstalk = config.get('Crosstalk', '')
    overwrite = config.get('overwrite', False)
    logfile = config.get('Logfile', '')
    participant_mapping = join(path_project, config.get('Participants_mapping_file', ''))
    logpath = join(config.get('Root', ''), config.get('Name', ''), 'logs')

    configure_logging(logpath, logfile)
    
    # Pipeline tracking removed - using simple JSON logging
    
    # Ensure log directory exists and initialize BIDS report if needed
    log_path = join(path_project, 'logs')
    os.makedirs(log_path, exist_ok=True)

    df, conversion_file = update_conversion_table(config)
    df = df.where(pd.notnull(df) & (df != ''), None)
    
    pmap = None
    if participant_mapping:
        try:
            pmap = pd.read_csv(participant_mapping, dtype=str)
        except Exception as e:
            print('Participant file not found, skipping')
            
    is_natmeg_id =  all(df['participant_from'].str.replace('sub-', '').astype(int) == df['participant_to'].astype(int))
    
    # Start by creating the BIDS directory structure
    unique_participants_sessions = df[['participant_to', 'session_to', 'datatype']].drop_duplicates()
    for _, row in unique_participants_sessions.iterrows():
        if is_natmeg_id:
            subject_padded = str(row['participant_to']).zfill(4)
        else:
            subject_padded = str(row['participant_to']).zfill(3)
        session_padded = str(row['session_to']).zfill(2)
        bids_path = BIDSPath(
            subject=subject_padded,
            session=session_padded,
            datatype=row['datatype'],
            root=path_BIDS
        ).mkdir()
        try:
            if row['datatype'] == 'meg':
                if not bids_path.meg_calibration_fpath:
                    write_meg_calibration(calibration, bids_path)
                if not bids_path.meg_crosstalk_fpath:
                    write_meg_crosstalk(crosstalk, bids_path)
        except Exception as e:
            log('BIDS', f"Error writing calibration/crosstalk files: {e}", level='error', logfile=logfile, logpath=logpath)
    
    # ignore split files as they are processed automatically
    if 'split' in df.columns:
        df = df[df['split'].isna() | (df['split'] == '')]

    # Flag deviants and exist if found
    deviants = df[df['status'] == 'check']
    if len(deviants) > 0:
        log('BIDS', 'Deviants found, please check the conversion table and run again', level='warning', logfile=logfile, logpath=logpath)
        # Still create BIDS report even when deviants found
        df.to_csv(conversion_file, sep='\t', index=False)
        update_bids_report(df, config)
        return

    n_files_to_process = len(df[df['status'] == 'run'])
    
    # Create progress bar for files to process

    pbar = tqdm(total=n_files_to_process, 
                desc=f"Bidsify files", 
                unit=" file(s)",
                disable=not sys.stdout.isatty(),
                ncols=80,
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
    pcount = 0
    for i, d in df.iterrows():
        # Skip files not ready for conversion
        if d['status'] in ['processed', 'skip'] and not overwrite:
            #print(f"{d['bids_name']} already converted")
            continue
        pcount += 1
        # if d[d['status'] == 'run']:
        print(f"Processing file {pcount}/{n_files_to_process}: {d['raw_name']}")
        # Update progress bar for each file being processed
        pbar.update(1)
        
        bids_path = None

        raw_file = f"{d['raw_path']}/{d['raw_name']}"

        bids_path, raw_info = bids_path_from_filename(raw_file,
                                            d['session_from'],
                                            config,
                                            pmap)

        event_id = d['event_id']
        events = None
        run = None
        if d['run']:
            run = d['run'].zfill(2)

        if event_id:
            with open(f"{path_BIDS}/../{event_id}", 'r') as f:
                event_id = json.load(f)
            events = mne.find_events(raw)

        # Create BIDS path
        bids_path.update(
            subject=subject_padded,
            session=d['session_to'].zfill(2),
            task=d['task'],
            acquisition=d['acquisition'],
            processing=d['processing'],
            description=d['description'],
            run=run
        )
        
        if bids_path.description and 'trans' in bids_path.description:
            trans = mne.read_trans(raw_file, verbose='error')
            mne.write_trans(bids_path, trans, overwrite=True)
                
        elif bids_path.suffix and 'headshape' in bids_path.suffix:
            headpos = mne.chpi.read_head_pos(raw_file)
            mne.chpi.write_head_pos(bids_path, headpos)

        elif bids_path.datatype in ['meg', 'eeg']:
        # Write the BIDS file
            try:
                raw = mne.io.read_raw_fif(raw_file, allow_maxshield=True, verbose='error') 
                write_raw_bids(
                    raw=raw,
                    bids_path=bids_path,
                    empty_room=None,
                    event_id=event_id,
                    events=events,
                    overwrite=True,
                    verbose='error'
                )
                
                # Operation tracked via JSON logging in update_bids_report()
                        
            except Exception as e:
                print(f"Error writing BIDS file: {e}")
                # If write_raw_bids fails, try to save the raw file directly
                # Fall back on raw.save if write_raw_bids fails
                fname = bids_path.copy().update(suffix=datatype, extension = '.fif').fpath
                try:
                    raw.save(fname, overwrite=True, verbose='error')
                except Exception as e:
                    print(f"Error saving raw file: {e}")
                    log('BIDS',
                        f'{fname} not bidsified',
                        level='error',
                        logfile=logfile,
                        logpath=logpath
                        )

            # Copy EEG to MEG
            if bids_path.datatype == 'eeg':
                copy_eeg_to_meg(raw_file, bids_path)

        # Add channel parameters 
        elif bids_path.acquisition == 'hedscan' and not bids_path.processing:
            
            opm_tsv = f"{d['raw_path']}/{d['raw_name']}".replace('raw.fif', 'channels.tsv')
            
            bids_tsv = bids_path.copy().update(suffix='channels', extension='.tsv')
            add_channel_parameters(bids_tsv, opm_tsv)
    
        # Update the conversion table        
        df.at[i, 'time_stamp'] = ts
        df.at[i, 'status'] = 'processed'
        df.at[i, 'bids_path'] = dirname(bids_path)
        df.at[i, 'bids_name'] = basename(bids_path)
        df.to_csv(conversion_file, sep='\t', index=False)

    # Close progress bar
    pbar.close()
    
    # Update BIDS processing report in JSON format for pipeline tracking
    update_bids_report(df, config)
    log('BIDS', f'All files bidsified according to {conversion_file}', level='info', logfile=logfile, logpath=logpath)
    
 
def update_bids_report(conversion_table: pd.DataFrame, config: dict):
    """
    Update the BIDS results report with processed entries in JSON format, 
    linking to the copy results for complete pipeline tracking.
    
    Creates a JSON report similar to copy_results.json but for BIDS conversions,
    allowing tracking of the complete pipeline from copy → BIDS.
    
    Args:
        conversion_table (pd.DataFrame): Conversion table with BIDS processing results
        config (dict): Configuration dictionary containing project paths
    
    Returns:
        int: Number of entries processed
    """
    project_root = join(config.get('Root', ''), config.get('Name', ''))
    log_path = join(project_root, 'logs')
    report_file = f'{log_path}/bids_results.json'
    
    # Load existing report if it exists
    existing_report = []
    if exists(report_file):
        try:
            with open(report_file, 'r') as f:
                existing_report = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing_report = []
    
    # Create a set of existing entries for duplicate detection
    existing_entries = set()
    for entry in existing_report:
        source_file = entry['Source File']
        bids_file = entry['BIDS File']
        
        # Convert lists to tuples for hashability
        if isinstance(source_file, list):
            source_file = tuple(source_file)
        if isinstance(bids_file, list):
            bids_file = tuple(bids_file)
            
        existing_entries.add((source_file, bids_file))
    
    # Group split files together by base filename
    df = conversion_table.drop_duplicates(subset=['raw_path', 'raw_name', 'bids_path', 'bids_name'])
    grouped_entries = {}
    for i, row in conversion_table.iterrows():
        source_file = f"{row['raw_path']}/{row['raw_name']}"
        source_base = re.sub(r'_raw-\d+\.fif$', '.fif', source_file)
        
        # Create a base key for grouping (remove split suffixes)
        
        source_files = get_split_file_parts(source_base)
        
        destination_files = (glob(row['bids_name'] + '*',
                 root_dir=row['bids_path']) + 
            glob(row['bids_name'].rsplit('_', 1)[0] + '_split*' + row['bids_name'].rsplit('_', 1)[1], 
                 root_dir=row['bids_path']))
    
        # TODO: update bids_results here as well
        # Initialize variables with defaults
        split = False
        bids_file = []
        
        if destination_files:
            if len(destination_files) > 1:
                split = True
                bids_file = destination_files
            else:
                split = False
                bids_file = destination_files[0]
        
        # Use source base + task + acquisition as the grouping key
        group_key = (source_base, row['task'], row['acquisition'], row.get('processing', ''))
        
        if group_key not in grouped_entries:
            grouped_entries[group_key] = {
                'source_files': [],
                'bids_files': [],
                'source_sizes': [],
                'bids_sizes': [],
                'row_data': row  # Keep first row's metadata
            }
        
        # Add files to the group
        grouped_entries[group_key]['source_files'].append(source_file)

        if split:
            grouped_entries[group_key]['bids_files'].extend(bids_file)
        else:
            if bids_file:  # Only append if bids_file is not empty
                grouped_entries[group_key]['bids_files'].append(bids_file)
        
        # Get file sizes
        source_size = None
        if exists(source_file):
            try:
                source_size = getsize(source_file)
            except (OSError, FileNotFoundError):
                source_size = None
        
        bids_size = None
        
        if split and bids_file:
            for file in bids_file:
                if exists(f"{row['bids_path']}/{file}"):
                    try:
                        if bids_size is None:
                            bids_size = 0
                        bids_size += getsize(f"{row['bids_path']}/{file}")
                    except (OSError, FileNotFoundError):
                        continue
        else:
            if bids_file and exists(f"{row['bids_path']}/{bids_file}"):
                try:
                    bids_size = getsize(f"{row['bids_path']}/{bids_file}")
                except (OSError, FileNotFoundError):
                    bids_size = None
        
        grouped_entries[group_key]['source_sizes'].append(source_size)
        grouped_entries[group_key]['bids_sizes'].append(bids_size)

    # Process grouped entries
    new_entries = []
    for group_key, group_data in grouped_entries.items():
        row = group_data['row_data']
        source_files = group_data['source_files']
        bids_files = group_data['bids_files']
        source_sizes = group_data['source_sizes']
        bids_sizes = group_data['bids_sizes']
        
        # Check if this group is already in the existing report
        # Use first source file and first bids file for duplicate detection
        primary_source = source_files[0] if source_files else ""
        primary_bids = bids_files if bids_files else ""
        
        # existing_entries contains tuples of (source_file, bids_file) where each
        # element may be a string or a tuple. Check for duplicates by testing
        # whether any existing entry contains the primary_source in its source
        # component (handles both single and grouped source entries).
        duplicate_found = False
        for existing_src, existing_bids in existing_entries:
            if existing_src == primary_source or (isinstance(existing_src, tuple) and primary_source in existing_src):
                duplicate_found = True
                break
        
        if not duplicate_found:
            # Sort source files: base file first, then splits in order
            # Create list of (source_file, bids_file, source_size, bids_size) tuples for sorting
            file_tuples = list(zip(source_files, [bids_files], source_sizes, bids_sizes))
            
            # Sort by source filename: base file (no -N suffix) first, then by split number
            def sort_key(file_tuple):
                source_file = file_tuple[0]
                filename = source_file.split('/')[-1]  # Get just the filename
                if '_raw-' in filename and filename.endswith('.fif'):
                    # Extract split number for sorting
                    import re
                    match = re.search(r'_raw-(\d+)\.fif$', filename)
                    if match:
                        return (1, int(match.group(1)))  # Split file: (1, split_number)
                return (0, 0)  # Base file comes first: (0, 0)
            
            file_tuples.sort(key=sort_key)
            
            # Unpack sorted tuples
            source_files, bids_files, source_sizes, bids_sizes = zip(*file_tuples) if file_tuples else ([], [], [], [])
            source_files, bids_files, source_sizes, bids_sizes = list(source_files), list(bids_files), list(source_sizes), list(bids_sizes)
            
            # Find actual BIDS filenames for split files using find_matching_paths
            if len(source_files) > 1:
                # Multiple files - find the actual BIDS files that were created
                # Parse the first BIDS path to get the directory and pattern info
                from pathlib import Path
                first_bids_path = Path(bids_files[0])
                bids_directory = first_bids_path.parent
                
                # Extract BIDS components from the first file to search for all related files
                # e.g., "sub-0953_ses-241104_task-Phalanges_acq-hedscan_meg.fif" or 
                # "sub-0953_ses-241104_task-Phalanges_acq-hedscan_proc-hpi_meg.fif"
                parts = first_bids_path.name.split('_')
                if len(parts) >= 4:
                    subject = parts[0]  # sub-0953
                    session = parts[1]  # ses-241104  
                    task = parts[2]     # task-Phalanges
                    acq = parts[3]      # acq-hedscan
                    
                    # Check if there's a processing component (proc-xxx)
                    processing = None
                    for part in parts[4:]:
                        if part.startswith('proc-'):
                            processing = part.replace('proc-', '')
                            break
                    
                    # Find all matching files (base + splits) using find_matching_paths
                    try:
                        find_params = {
                            'root': str(bids_directory),
                            'subjects': [subject.replace('sub-', '')],
                            'sessions': [session.replace('ses-', '')],
                            'tasks': [task.replace('task-', '')], 
                            'acquisitions': [acq.replace('acq-', '')],
                            'suffixes': 'meg',
                            'extensions': '.fif'
                        }
                        
                        # Add processing parameter if it exists
                        if processing:
                            find_params['processings'] = [processing]
                        
                        matching_paths = find_matching_paths(**find_params)
                        
                        if matching_paths:
                            # Convert BIDSPath objects to relative paths and sort them properly
                            found_bids_files = []
                            for p in matching_paths:
                                # The BIDSPath.fpath gives us the full path to the file
                                # We need to convert this to a path relative to our project root
                                abs_path = str(p.fpath)
                                
                                # Build the expected BIDS relative path from project root
                                # Format: neuro/data/local/OPM-benchmarking/BIDS/sub-XX/ses-XX/meg/filename.fif
                                project_root = config.get('Root', '')
                                project_name = config.get('Name', '')
                                
                                if project_root and project_name:
                                    # Create path relative to project root
                                    bids_rel_path = f"{project_root}/{project_name}/BIDS/{p.fpath.name}"
                                    # But we need the full BIDS structure, so let's construct it properly
                                    bids_structure = f"sub-{p.subject}/ses-{p.session}/{p.datatype}/{p.fpath.name}"
                                    bids_rel_path = f"{project_root}/{project_name}/BIDS/{bids_structure}"
                                else:
                                    # Fallback to absolute path
                                    bids_rel_path = abs_path
                                    
                                found_bids_files.append(bids_rel_path)
                            
                            # Sort: base file first, then splits in order
                            def bids_sort_key(filepath):
                                filename = Path(filepath).name
                                if '_split-' in filename:
                                    # Extract split number for sorting splits
                                    import re
                                    match = re.search(r'_split-(\d+)_', filename)
                                    if match:
                                        return (1, int(match.group(1)))  # Split file: (1, split_number)
                                return (0, 0)  # Base file comes first: (0, 0)
                            
                            found_bids_files.sort(key=bids_sort_key)
                            bids_files = found_bids_files
                    except Exception as e:
                        # Fallback to original files if find_matching_paths fails
                        print(f"Warning: Could not find matching BIDS files: {e}")
                        pass
            
            # Calculate total sizes
            total_source_size = sum(size for size in source_sizes if size is not None) if source_sizes else None
            total_bids_size = sum(size for size in bids_sizes if size is not None) if any(size is not None for size in bids_sizes) else None
            
            # Determine if this is a split file group or single file
            if len(source_files) > 1:
                # Multiple files - use arrays
                source_file_entry = source_files
                bids_file_entry = bids_files
                split_info = None  # Set to None for consolidated entries
            else:
                # Single file - use string (compatible with existing format)
                source_file_entry = source_files[0] if source_files else ""
                bids_file_entry = bids_files[0] if bids_files else ""
                split_info = row['split'] if pd.notna(row['split']) and row['split'] != '' else None
            
            new_entries.append({
                'Source File': source_file_entry,
                'Processing Date': row['time_stamp'],
                'BIDS File': bids_file_entry,
                'Source Size': total_source_size,
                'BIDS Size': total_bids_size,
                'Participant': row['participant_to'],
                'Session': row['session_to'], 
                'Task': row['task'],
                'Split': split_info,
                'Acquisition': row['acquisition'],
                'Datatype': row['datatype'],
                'Processing': row['processing'] if row['processing'] else None,
                'Conversion Status': 'Success' if row['status'] == 'processed' else row['status'].title(),
                'timestamp': datetime.now().isoformat()
            })
    
    # Combine existing and new entries
    updated_report = existing_report + new_entries

    # Write updated report back to file
    with open(report_file, 'w') as f:
        json.dump(updated_report, f, indent=4)
    
    # Log summary
    logfile = config.get('Logfile', 'bidsify.log')
    logpath = join(config.get('Root', ''), config.get('Name', ''), 'logs')
    log('BIDS', f'BIDS report updated: {len(new_entries)} new entries added to existing {len(existing_report)} entries',
        logfile=logfile, logpath=logpath)
    
    return len(new_entries)   

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
    create_proc_description(config)
    bidsify(config)
    update_sidecars(config)
    # print_dir_tree(config['BIDS'])
    return True
    

if __name__ == "__main__":
    main()
