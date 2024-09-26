#!/opt/miniconda3/envs/mne/bin/python

# -*- coding: utf-8 -*-

# #!/opt/miniconda3/envs/mne/bin/python
# #!/home/natmeg/miniforge3/envs/mne/bin/python
import pandas as pd
import json
import re
import os
from shutil import copy2
from os.path import exists
import sys
from glob import glob
import numpy as np

from mne_bids import (
    BIDSPath,
    write_raw_bids,
    update_sidecar_json,
    make_dataset_description,
    write_meg_calibration,
    write_meg_crosstalk,
    )
import mne

from tkinter.filedialog import askdirectory, askopenfilename

###############################################################################
# Global variables
###############################################################################
noise_patterns = ['empty', 'noise', 'Empty']
proc = 'sss'  # ['mc', 'sss', 'corr98']

###############################################################################
# Functions: Create or fill templates: dataset description, participants info
###############################################################################


def ask_user_overwrite(path):
    overwrite_bids = input("Do you want to overwrite existing files at the output folder %s/BIDS? "
                           "('Y' or 'N' (default). You can press Enter for default option (no overwrite).\n" % path)
    if overwrite_bids == 'Y' or overwrite_bids == 'y':
        return True
    return False


def create_dataset_description(root_path, path_BIDS, overwrite=False):
    # Ask user to prompt the different fields for dataset description
    output_path = f'{path_BIDS}/BIDS'
    if not exists(output_path):
        os.makedirs(output_path)
    file_exists = exists(f'{root_path}/dataset_description.json')
    file_exists1 = exists(f'{output_path}/dataset_description.json')
    if not (file_exists or file_exists1) or overwrite:
        name = input('Write the name for your dataset. If you want to skip press Enter.\n')
        dataset_type = input(
            'Choose the interpretation for your dataset. '
            'Write ‘raw’ or ‘derivative’ (default is raw). '
            'If you want to skip press Enter.\n')
        if dataset_type == '':
            dataset_type = 'raw'
        data_license = input('Write the license for the dataset. If you want to skip press Enter.\n')
        if data_license == '':
            data_license = None
        authors = input(
            'Write the list of individuals who contributed to the creation/curation of the dataset. '
            'If you want to skip press Enter.\n')
        if authors == '':
            authors = None
        acknowledgements = input(
            'Write the text acknowledging contributions of individuals or institutions beyond those '
            'listed in Authors or Funding. If you want to skip press Enter.\n')
        if acknowledgements == '':
            acknowledgements = None
        how_to_acknowledge = input('Write how to acknowledge your dataset. If you want to skip press Enter.\n')
        if how_to_acknowledge == '':
            how_to_acknowledge = None
        funding = input('Write the list of sources of funding (grant numbers). If you want to skip press Enter.\n')
        if funding == '':
            funding = None
        ethics_approvals = input(
            'Write the list of ethics committee approvals of the research protocols and/or protocol identifiers. '
            'If you want to skip press Enter.\n')
        if ethics_approvals == '':
            ethics_approvals = None
        references_and_links = input(
            'Write possible list of references to publications that contain information on the dataset. '
            'If you want to skip press Enter.\n')
        if references_and_links == '':
            references_and_links = None
        doi = input('Write the doi for your dataset. If you want to skip press Enter.\n')
        if doi == '':
            doi = None
        make_dataset_description(
            path=output_path,
            name=name,
            dataset_type=dataset_type,
            data_license=data_license,
            authors=authors,
            acknowledgements=acknowledgements,
            how_to_acknowledge=how_to_acknowledge,
            funding=funding,
            ethics_approvals=ethics_approvals,
            references_and_links=references_and_links,
            doi=doi,
            overwrite=overwrite
        )


def check_create_participants_files(root_path, path_BIDS, overwrite=False):
    # check if participants.tsv and participants.json files is available or create a new one with default fields
    output_path = f'{path_BIDS}/BIDS'
    if not exists(output_path):
        os.makedirs(output_path)
    tsvfile_exists = exists(f'{root_path}/participants.tsv')
    tsvfile_exists1 = exists(f'{output_path}/participants.tsv')
    if not (tsvfile_exists or tsvfile_exists1) or overwrite:
        # create default fields participants.tsv
        participants = glob('NatMEG*', root_dir=root_path)
        # create empty table with 4 columns (participant_id, sex, age)
        df = pd.DataFrame(columns=['participant_id', 'sex', 'age', 'group'])
        pattern = re.compile(r'NatMEG_')
        participants = pd.DataFrame([pattern.sub('', sub) for sub in participants])
        participants[0] = participants[0].apply(lambda x: f"sub-{x}")
        df['participant_id'] = participants
        df['sex'] = pd.DataFrame(['n/a'] * len(participants))  # string, default n/a
        df['age'] = pd.DataFrame([np.nan] * len(participants))  # number, default nan
        df['group'] = pd.DataFrame(['control'] * len(participants))  # string, default group is control
        df.to_csv(f'{output_path}/participants.tsv', sep='\t', index=False)
        print(f'Writing {output_path}/participants.tsv')

    jsonfile_exists = exists(f'{root_path}/participants.json')
    jsonfile_exists1 = exists(f'{output_path}/participants.json')
    if not (jsonfile_exists or jsonfile_exists1) or overwrite:
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
# Functions: MEG and OPM to bids format
###############################################################################


def add_calibration_crosstalk(crosstalk_fname, calibration_fname, bids_path):
    # Add calibration and cross talk
    if not bids_path.meg_calibration_fpath:
        write_meg_calibration(calibration_fname, bids_path)
    if not bids_path.meg_crosstalk_fpath:
        write_meg_crosstalk(crosstalk_fname, bids_path)


def move_rename_OPM(path_OPM, path_BIDS, overwrite=False):
    """
    For each participant and session within OPM folder, move the files to BIDS correspondent folder
    or create a new one if the session does not match. Change the name of the files into BIDS format.
    """
    if path_OPM != '':
        # there is OPM folder
        for participant_folder in os.listdir(path_OPM):
            if participant_folder.startswith('sub-'):
                participant = participant_folder.split('-')[-1]
                participant_path = os.path.join(path_OPM, participant_folder)
                print("Processing the participant: %s." % participant_path)

                # Loop over each raw opm file and read the session
                all_fifs_files = glob(f'{participant_path}/*.fif')
                all_tsv_files = glob(f'{participant_path}/*_channels.tsv')
                for raw_file in os.listdir(participant_path):
                    raw_fname = os.path.join(participant_path, raw_file)
                    # get session
                    session = raw_file.split('_')[0]

                    # check that file is in all_fifs_files
                    if raw_fname in all_fifs_files and not raw_file.startswith('.'):
                        # Get task
                        task = raw_file.split('_')[-2].split('-')[-1]
                        # get split
                        endsplit = raw_file.split('_')[-1].split('.')[0].split('-')[-1]
                        if endsplit.isnumeric():
                            split = int(endsplit) + 1
                        else:
                            split = 1

                        # rename with bids name
                        task = task.replace('_', '')

                        if split != 1:
                            new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/sub-{participant}'
                                        f'_ses-{session[-6:]}_task-{task}_acq-opm_split-{split}_proc-raw_meg.fif')
                            new_name_tsv = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/sub'
                                            f'-{participant}_ses-{session[-6:]}_task-{task}_acq-opm_split-{split}'
                                            f'_proc-raw_channels.tsv')
                        else:
                            new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/sub-{participant}'
                                        f'_ses-{session[-6:]}_task-{task}_acq-opm_proc-raw_meg.fif')
                            new_name_tsv = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/'
                                            f'sub-{participant}_ses-{session[-6:]}_task-{task}_acq-opm'
                                            f'_proc-raw_channels.tsv')

                        if split == 1 and (not exists(new_name) or overwrite):
                            print("Converting to BIDS the file: %s." % raw_fname)
                            # Create BIDSPath for the raw data
                            bids_path = BIDSPath(
                                subject=participant,
                                datatype='meg',
                                session=session[-6:],
                                task=task,
                                acquisition='opm',
                                root=f'{path_BIDS}/BIDS',
                                suffix='meg',
                                processing='raw'
                            )
                            try:
                                # Read raw data
                                rawf = mne.io.read_raw(raw_fname, allow_maxshield=True, verbose='error')
                                # Specify power line frequency as required by BIDS
                                rawf.info['line_freq'] = 50
                                rawf.drop_channels([c for c in rawf.info['ch_names'] if 'CHPI' in c])

                                # Write raw BIDS data
                                write_raw_bids(
                                    raw=rawf,
                                    bids_path=bids_path,
                                    empty_room=None,
                                    events=None,
                                    overwrite=True,
                                    verbose=False  # Set verbose to True if you want more information
                                )
                            except Exception as e:
                                # print(f"An error occurred while processing the file: {e}")
                                # move these files under BIDS folder/participant
                                output_path = f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/'
                                if not exists(output_path) and not raw_file.startswith('.'):
                                    os.makedirs(os.path.dirname(output_path))

                                old_name = f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/{raw_file}'

                                if not exists(new_name) or overwrite:
                                    copy2(raw_fname, output_path)
                                    os.rename(old_name, new_name)

                                # check if there is an associated channels tsv file and copy it
                                tsv_raw_file = raw_file.replace('raw.fif', 'channels.tsv')
                                old_name_tsv = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/'
                                                f'meg/{tsv_raw_file}')
                                if exists(os.path.join(participant_path, tsv_raw_file)) and (
                                        not exists(new_name_tsv) or overwrite):
                                    copy2(os.path.join(participant_path, tsv_raw_file), output_path)
                                    os.rename(old_name_tsv, new_name_tsv)

                    elif raw_fname not in all_tsv_files and not raw_file.startswith('.'):
                        # copy other files to the new folder, under BIDS folder/participant
                        output_path = f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/'
                        if not exists(output_path):
                            os.makedirs(os.path.dirname(output_path))
                        if not exists(os.path.join(output_path, raw_file)) or overwrite:
                            copy2(raw_fname, output_path)


def contains_noise_patterns(string, noisepatterns):
    for pattern in noisepatterns:
        if pattern in string:
            return True
    return False


def contains_proc(string, p):
    if p in string:
        return True
    return False


def move_rename_MEG(path_MEG, path_BIDS, path_OPM, crosstalk, calibration, overwrite=False):
    """
    For each participant and session within MEG folder, move the files to BIDS correspondent folder
    or create a new one if the session does not match. Change the name of the files into BIDS format.
    """
    error_files_list = []
    if path_MEG != '' and str(path_MEG) != '()':
        # there is MEG folder
        for participant_folder in os.listdir(path_MEG):
            if participant_folder.startswith('NatMEG_'):
                participant = participant_folder.split('_')[-1]
                participant_path = os.path.join(path_MEG, participant_folder)
                print("Processing the participant: %s." % participant_path)
                # Loop over each session folder for the participant
                for session_folder in os.listdir(participant_path):
                    if not session_folder.startswith('.'):
                        session = session_folder
                        session_path = os.path.join(participant_path, session_folder)

                        # Loop over each raw MEG file and find the one from empty room within this session
                        all_fifs_files = glob(f'{session_path}/meg/*.fif')
                        empty_fname = []
                        for raw_file in all_fifs_files:
                            if contains_noise_patterns(raw_file, noise_patterns):
                                empty_fname.append(raw_file)

                        # Loop over each empty room file before:
                        associated_er_path = []
                        for raw_file in empty_fname:
                            all_fifs_files.remove(raw_file)
                            # Get task
                            task = raw_file.split('/')[-1].split('.')[0].split('-')[0]
                            # get split
                            endsplit = raw_file.split('/')[-1].split('.')[0].split('-')[-1]
                            if endsplit.isnumeric():
                                split = int(endsplit) + 1
                            else:
                                split = 1
                            task = task.replace('_', '')
                            task = f'noise{task}'

                            if path_OPM != '':
                                # Create BIDSPath for the raw data
                                bids_path = BIDSPath(
                                    subject=participant,
                                    datatype='meg',
                                    session=session,
                                    task=task,
                                    acquisition='squid',
                                    root=f'{path_BIDS}/BIDS',
                                    suffix='meg'
                                )
                                new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session}/meg/sub-{participant}'
                                            f'_ses-{session}_task-{task}_acq-squid_meg.fif')
                            else:
                                bids_path = BIDSPath(
                                    subject=participant,
                                    datatype='meg',
                                    session=session,
                                    task=task,
                                    root=f'{path_BIDS}/BIDS',
                                    suffix='meg'
                                )
                                new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session}/meg/sub-{participant}'
                                            f'_ses-{session}_task-{task}_meg.fif')

                            if split == 1 and (not exists(new_name) or overwrite):
                                print("Converting to BIDS the file: %s." % raw_file)
                                add_calibration_crosstalk(crosstalk, calibration, bids_path)
                                try:
                                    rawfif = mne.io.read_raw_fif(raw_file, allow_maxshield=True, verbose='error')
                                    rawfif.info['line_freq'] = 50
                                    rawfif.drop_channels([c for c in rawfif.info['ch_names'] if 'CHPI' in c])

                                    # Write raw BIDS data
                                    write_raw_bids(
                                        raw=rawfif,
                                        bids_path=bids_path,
                                        empty_room=None,
                                        events=None,
                                        overwrite=True,
                                        verbose=False
                                    )
                                    associated_er_path.append(str(bids_path.fpath))
                                    # update sidecar
                                    sidecar_updates = {
                                        'AssociatedEmptyRoom': [],
                                    }
                                    sidecar_path = bids_path.copy().update(check=True, suffix='meg', extension='.json')
                                    update_sidecar_json(bids_path=sidecar_path, entries=sidecar_updates)
                                except Exception as e:
                                    print(f"An error occurred while processing the file: {e}")
                                    # copy file as it is to new folder
                                    output_path = f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/meg/'
                                    if not exists(output_path):
                                        os.makedirs(os.path.dirname(output_path))
                                    print(not exists(os.path.join(output_path, raw_file.split('/')[-1])))
                                    if not exists(os.path.join(output_path, raw_file.split('/')[-1])) or overwrite:
                                        copy2(raw_file, output_path)
                                        # save name of file in error_reports
                                        error_files_list.append(os.path.join(output_path, raw_file.split('/')[-1]))

                        # Loop over each raw MEG file
                        for raw_file in os.listdir(f'{session_path}/meg'):
                            raw_fname = os.path.join(f'{session_path}/meg', raw_file)
                            # check that file is in all_fifs_files
                            if raw_fname in all_fifs_files:
                                # Get task
                                task = raw_file.split('.')[0].split('-')[0]
                                # check if its EEG, if not MEG
                                modality = "meg"
                                file_info = mne.io.read_info(raw_fname)
                                channel37 = mne.channel_type(file_info, 37) # might be different number the one to always differentiate EEG form MEG
                                if channel37 != 'mag':
                                    modality = "eeg"

                                # get split
                                endsplit = raw_file.split('.')[0].split('-')[-1]
                                if endsplit.isnumeric():
                                    split = int(endsplit) + 1
                                else:
                                    split = 1

                                if contains_proc(task, proc):
                                    proc_steps = task.split('_')[1:]
                                    proc_steps = "+".join(proc_steps)
                                    task = task.split('_')[0]
                                    task = task.replace('_', '')
                                    if path_OPM != '':
                                        # Create BIDSPath for the raw data
                                        bids_path = BIDSPath(
                                            subject=participant,
                                            datatype=modality,
                                            session=session,
                                            task=task,
                                            acquisition='squid',
                                            root=f'{path_BIDS}/BIDS',
                                            suffix=modality,
                                            processing=proc_steps
                                        )
                                        new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session}/{modality}/sub'
                                                    f'-{participant}_ses-{session}_task-{task}_acq-squid'
                                                    f'_proc-{proc_steps}_{modality}.fif')
                                    else:
                                        # Create BIDSPath for the raw data
                                        bids_path = BIDSPath(
                                            subject=participant,
                                            datatype=modality,
                                            session=session,
                                            task=task,
                                            root=f'{path_BIDS}/BIDS',
                                            suffix=modality,
                                            processing=proc_steps
                                        )
                                        new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session}/{modality}/sub'
                                                    f'-{participant}_ses-{session}_task-{task}'
                                                    f'_proc-{proc_steps}_{modality}.fif')

                                else:
                                    task = task.replace('_', '')
                                    if path_OPM != '':
                                        # Create BIDSPath for the raw data
                                        bids_path = BIDSPath(
                                            subject=participant,
                                            datatype=modality,
                                            session=session,
                                            task=task,
                                            acquisition='squid',
                                            root=f'{path_BIDS}/BIDS',
                                            suffix=modality,
                                            processing='raw'
                                        )
                                        new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session}/{modality}/sub'
                                                    f'-{participant}_ses-{session}_task-{task}'
                                                    f'_acq-squid_proc-raw_{modality}.fif')
                                    else:
                                        bids_path = BIDSPath(
                                            subject=participant,
                                            datatype=modality,
                                            session=session,
                                            task=task,
                                            root=f'{path_BIDS}/BIDS',
                                            suffix=modality,
                                            processing='raw'
                                        )
                                        new_name = (f'{path_BIDS}/BIDS/sub-{participant}/ses-{session}/{modality}/sub'
                                                    f'-{participant}_ses-{session}_task-{task}_proc-raw_{modality}.fif')

                                if split == 1 and not exists(new_name) or overwrite:
                                    try:
                                        if modality == "meg":
                                            add_calibration_crosstalk(crosstalk, calibration, bids_path)
                                        print("Converting to BIDS the file: %s." % raw_fname)
                                        # Read raw data
                                        rawfif = mne.io.read_raw_fif(raw_fname, allow_maxshield=True, verbose='error')
                                        # Specify power line frequency as required by BIDS
                                        rawfif.info['line_freq'] = 50

                                        rawfif.drop_channels([c for c in rawfif.info['ch_names'] if 'CHPI' in c])

                                        # Write raw BIDS data
                                        write_raw_bids(
                                            raw=rawfif,
                                            bids_path=bids_path,
                                            empty_room=None,
                                            events=None,
                                            overwrite=True,
                                            verbose=False  # Set verbose to True if you want more information
                                        )
                                        if modality == "meg":
                                            # update sidecar
                                            sidecar_updates = {
                                                'AssociatedEmptyRoom': [sub.split('/')[-1] for sub in
                                                                        associated_er_path],
                                            }
                                            sidecar_path = bids_path.copy().update(check=True, suffix=modality,
                                                                                   extension='.json')
                                            update_sidecar_json(bids_path=sidecar_path, entries=sidecar_updates)

                                    except Exception as e:
                                        print(f"An error occurred while processing the file: {e}")
                                        # copy file as it is to new folder
                                        output_path = f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/{modality}/'
                                        if not exists(output_path):
                                            os.makedirs(os.path.dirname(output_path))
                                        if not exists(os.path.join(output_path, raw_file)) or overwrite:
                                            try:
                                                copy2(raw_fname, output_path)
                                            except PermissionError:
                                                if sys.platform == 'darwin':
                                                    os.system('chflags nouchg {}'.format(os.path.join(output_path, raw_file)))
                                                    copy2(raw_fname, output_path)
                                                else:
                                                    raise
                                            # save name of file in error_reports
                                            error_files_list.append(os.path.join(output_path, raw_file))
                            elif raw_fname not in empty_fname and not raw_file.startswith('.'):
                                modality = "meg"
                                if contains_proc(raw_fname.split('/')[-1].split('.')[0], "EEG"):
                                    modality = "eeg"
                                # copy other files to the new folder, under BIDS folder/participant
                                output_path = f'{path_BIDS}/BIDS/sub-{participant}/ses-{session[-6:]}/{modality}/'
                                if not exists(output_path):
                                    os.makedirs(os.path.dirname(output_path))
                                if ((not exists(os.path.join(output_path, raw_file)) or overwrite) and
                                        not os.path.isdir(raw_fname)):
                                    try:
                                        copy2(raw_fname, output_path)
                                    except PermissionError:
                                        if sys.platform == 'darwin':
                                            os.system('chflags nouchg {}'.format(os.path.join(output_path, raw_file)))
                                            copy2(raw_fname, output_path)
                                        else:
                                            raise
                                    # save name of file in error_reports
                                    error_files_list.append(os.path.join(output_path, raw_file))
    return error_files_list

###############################################################################
# Functions: Ask directories and files
###############################################################################


def ask_directories_MEG_OPM_BIDS():
    # Ask directories of MEG and OPM data
    print("Select Folder for MEG data")
    path_MEG = askdirectory(title='Select Folder for MEG data')  # shows dialog box and return the MEG path
    if str(path_MEG) == '()' or path_MEG == '':
        print("You need to select a folder with MEG/EEG data.")
        sys.exit()
    else:
        print("The folder selected for MEG data is %s." % str(path_MEG))
    print("Select Folder for OPM data. If you don't have OPM, just cancel the selection")
    path_OPM = askdirectory(title='Select Folder for OPM data')  # shows dialog box and return the OPM path
    if str(path_OPM) == '()' or path_OPM == '':
        print("You did not select a folder for OPM data. We assume you only have MEG/EEG data.")
        path_OPM = ''
    else:
        print("The folder selected for OPM data is %s." % str(path_OPM))
    print("Select Folder where to create your output BIDS folder data. "
          "It should be different directory than MEG and OPM folder")
    path_BIDS = askdirectory(title='Select Folder for output data')   # shows dialog box and return the BIDS path
    if str(path_BIDS) == '()' or path_BIDS == '':
        print("You need to select a folder for the output data.")
        sys.exit()
    else:
        print("The folder selected for BIDS output data is %s." % str(path_BIDS))

    return path_MEG, path_OPM, path_BIDS


def ask_MEG_calibration_crosstalk_files():
    default_path_calibration = '/neuro/databases/sss/sss_cal.dat'
    default_path_crosstalk = '/neuro/databases/ctc/ct_sparse.fif'

    # Ask files of calibration and crosstalk files
    print("Select File for calibration. Press Cancel if you want to use the default one ('sss_cal.dat').")
    # calibration = '../neuro/databases/sss/sss_cal.dat'
    calibration = askopenfilename(
        title='Select File for calibration. Press Cancel if you want '
              'to use the default one (sss_cal.dat).')  # shows dialog box and return the calibration path
    if str(calibration) == '()' or calibration == '':
        calibration = default_path_calibration
    print("The file selected for calibration is %s." % calibration)

    print("Select File for cross-talk. Press Cancel if you want to use the default one ('ct_sparse.fif').")
    # crosstalk = '../neuro/databases/ctc/ct_sparse.fif'
    crosstalk = askopenfilename(title='Select File for cross-talk. Press Cancel if you want to use '
                                      'the default one (ct_sparse.fif).')  # shows dialog box and return the OPM path
    if str(crosstalk) == '()' or crosstalk == '':
        crosstalk = default_path_crosstalk
    print("The file selected for cross-talk is %s." % crosstalk)
    return calibration, crosstalk


def write_errors_file(list_err, path, overwrite=False):
    df = pd.DataFrame(list_err)
    if not exists(f'{path}/error_files_list.txt') or overwrite or not os.path.getsize(f'{path}/error_files_list.txt') > 1:
        df.to_csv(f'{path}/error_files_list.txt', sep='\t', index=False)
    else:
        df_read = pd.read_csv(f'{path}/error_files_list.txt')
        new_df = pd.concat([df_read, df], axis=0)  # concatenate vertically
        new_df.to_csv(f'{path}/error_files_list.txt', sep='\t', index=False)


def main():
    # Ask user to input directories, files, and data to create default metadata
    path_MEG, path_OPM, path_BIDS = ask_directories_MEG_OPM_BIDS()  # Ask directories of MEG and OPM data
    # Ask files for MEG calibration and crosstalk
    calibration, crosstalk = ask_MEG_calibration_crosstalk_files()
    overwrite_bids = ask_user_overwrite(path_BIDS)  # Ask the user if overwrite existing files
    # create dataset description file if the file does not exist or overwrite_bids is True
    create_dataset_description(path_MEG, path_BIDS, overwrite_bids)
    # create participant files if files don't exist at MEG directory or overwrite_bids is True
    check_create_participants_files(path_MEG, path_BIDS, overwrite_bids)
    # Bidsify OPM if there is OPM folder
    move_rename_OPM(path_OPM, path_BIDS, overwrite_bids)
    # Bidsify MEG data
    err_files = move_rename_MEG(path_MEG, path_BIDS, path_OPM, crosstalk, calibration, overwrite_bids)
    # write err files in BIDS folder
    write_errors_file(err_files, f'{path_BIDS}/BIDS/', overwrite_bids)


if __name__ == "__main__":
    main()
