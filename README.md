---
title: Utility scripts for NatMEG
---

# Bidsify
This script converts data from NatMEG (MEG, EEG, OPM) to BIDS format and organizes the data into a BIDS-compliant folder structure. The script is designed to work with data collected at NatMEG and is based on the MNE-BIDS library.

## Prerequisits
Ensure you have the following non-defualt libraries installed in your Python environment: `mne`, `mne_bids`, `numpy`, `pandas`

## Process

### Install requirements
1. Make sure python modules are installed in the environment. If not, install them using the following commands:

```bash
conda install mne mne-bids
```

## Components 

### Config file

A configuration file is needed and you will be prompted to create a defaul file if it does not exist.

#### Example

```json
{
    "squidMEG": "/neuro/data/sinuhe/opm",
    "opmMEG": "/neuro/data/kaptah/OPMbenchmarking1",
    "BIDS": "/neuro/data/local/OPM-benchmarking",
    "Calibration": "/neuro/databases/sss/sss_cal.dat",
    "Crosstalk": "/neuro/databases/ctc/ct_sparse.fif",
    "Dataset_description": "dataset_description.json",
    "Participants": "participants.tsv",
    "Participants mapping (csv)": "/neuro/data/local/OPM-benchmarking/mapping.csv",
    "Original subjID name": "old_subject_id",
    "New subjID name": "new_subject_id",
    "Original session name": "old_session_id",
    "New session name": "new_session_id",
    "Overwrite": "on"
}
```

#### Description

- `squidMEG`: Path to the raw data folder for SQUID MEG data
- `opmMEG`: Path to the raw data folder for OPM MEG data
- `BIDS`: Path to the BIDS folder where the data will be saved
- `Calibration`: Path to the calibration file
- `Crosstalk`: Path to the crosstalk file
- `Dataset_description`: Path to the dataset_description.json file in the BIDS folder
- `Participants`: Path to the participants.tsv file in the BIDS folder
- `Participants mapping (csv)`: Path to the mapping file that contains the original and new subject IDs
- `Original subjID name`: Name of the column in the mapping file that contains the original subject ID
- `New subjID name`: Name of the column in the mapping file that contains the new subject ID
- `Original session name`: Name of the column in the mapping file that contains the original session ID
- `New session name`: Name of the column in the mapping file that contains the new session ID
- `Overwrite`: If set to "on", the script will overwrite existing files in the BIDS folder

### The conversion table
A conversion table will be created when running `bidsify.py`. This conversion file estimates task names, processing, and other parameters to create the bidsified file name. The conversion table is then looped through, skipping split-files and already converted files. By editing the lates file, you can change deviant task names, and decide to whether to run the conversion on a specific file or not. The conversion table is saved in the conversion_logs folder as `<date_of_creationg>_bids_conversion_table.csv`. By default the latest file will be used but you can also select your own file by adding the `--conversion` flag to the command line.

#### Header description

- `time_stamp`: The timestamp when the original conversion file was created.
- `run_conversion`: Indicates whether the conversion should be executed (`yes` or `no`).
- `task_count`: N tasks that are unique to participant, session and acquisition, and datatype.
- `task_flag`: Flag `ok` if task_count is not 1, else `check`.
- `participant_from`: The original participant ID.
- `participant_to`: The new participant ID after mapping.
- `session_from`: The original session ID.
- `session_to`: The new session ID after mapping.
- `task`: The task name associated with the file.
- `split`: Indicates if the file is a split file.
- `run`: If more than one occurence of a task in the same session this should be set modifided manually.
- `datatype`: The type of data according to BIDS (e.g., `meg`, `eeg`).
- `acquisition`: Acquisition device.
- `processing`: Pre-processing details for the data, eg. MaxFilter.
- `raw_path`: The path to the raw data file.
- `raw_name`: The name of the raw data file.
- `bids_path`: The path where the BIDS-compliant file will be saved.
- `bids_name`: The name of the BIDS-compliant file.

> If task_flag is `check`. You will be prompted to edit the conversion file before continuing. This is to ensure that the task name is correct and that the file is not a split file. If you are sure that the task name is correct, you can set the task_flag to `ok` and continue with the conversion.

### Run script examples

Example 1. Run the script by executing the following command:

```bash
python bidsify.py --config=path/to/name_of_config.json
```

This will run the script with the config file without further questions using the latest created conversion file.

Example 2. Edit config file before running the script:

```bash
python bidsify.py --config=path/to/name_of_config.json --edit
```
This will open a dialog for you to edit the config file before running the script.

Example 3. Run the script without a config flag
```bash
python bidsify.py # (add --edit to also edit an existing file)
```
You will get three options in the terminal
- `open`: Open an existing config file (default)
- `new`: Create a new config file from a default template using the dialog
- `cancel`: Cancel the operation

Example 4. Run the script with a specific config and conversion file:
```bash
python bidsify.py --config=path/to/name_of_config.json --conversion=path/to/conversion_file.csv
```
Runs conversion without any further questions using a specific conversion file. 

### BIDS descriptions

1. If a `dataset_description.json` is not defined in the configuration file a dialog will open for you to fill in the necessary fields.

2. If a `participants.tsv` file is not defined in the configuration file a default one will be created.

3. The script will loop through all participants and sessions. Read all files from the raw folders, convert them to BIDS format and write locally. 

### Naming conventions
Although the script is written to handle various breaches of naming convensions, it is not yet water tight. The following naming conventions are recommended:

- Do not use numbers in your task name when saving your raw data.  
- Do not use `_` in the file-name. Tasks named `my_great_task` will be renamed to `MyGreatTask`.
- Empty room recordings should include the word `empty` or `noise` in the filename followed by `before` or `after` to indicate if it was recorded before or after the experiment.
- Resting state should be begin with `rest`, conversions for resting state names like `RS` is not yet implemented.

## Special features

- EEG data will be placed in an `eeg` folder in the BIDS root directory according to BIDS specifications. However, as EEG data is collected through the TRIUX system a `.fif` file will be created and the `.json` sidecare will be copied to the `meg` folder.

# Maxfilter script for NatMEG

## Prerequisits
Ensure you have the following non-default libraries installed in your Python environment: `mne`, `matplotlib`

## Process

### Install requirements

1. Make sure python modules are installed in the environment. If not, install them using the following commands:

```bash
conda install mne matplotlib
```

### Run script

Option 1. Run the script by executing the following command:

```bash
python maxfilter.py --config=path/to/maxfilter_settings.json
```
This will run the script with the config file wihout further questions.

Option 2. Edit config file before running the script:

```bash
python maxfilter.py --config=path/to/maxfilter_settings.json --edit
```
This will open a dialog for you to edit the config file before running the script.

Option 3. Run the script without a config flag
```bash
python maxfilter.py # (add --edit to also edit an existing file)
```
You will get three options in the terminal
- `open`: Open an existing config file (default)
- `new`: Create a new config file from a default template using the dialog
- `cancel`: Cancel the operation

### Config file

```json
{
"standard_settings": {
    "project_name": "",
    "trans_conditions": ["task1", "task2"],
    "trans_option": "mne_continous",
    "merge_runs": "on",
    "empty_room_files": ["empty_room_before.fif", "empty_room_after.fif"],
    "sss_files": ["empty_room_before.fif", "empty_room_after.fif"],
    "autobad": "on",
    "badlimit": 7,
    "bad_channels":[""],
    "tsss_default": "on",
    "correlation": 0.98,
    "movecomp_default": "on",
    "data_path": "."
    },

"advanced_settings": {
    "force": "off",
    "downsample": "off",
    "downsample_factor": 4,
    "apply_linefreq": "off",
    "linefreq_Hz": 50,
    "scripts_path": "/home/natmeg/Scripts",
    "cal": "/neuro/databases/sss/sss_cal.dat",
    "ctc": "/neuro/databases/ctc/ct_sparse.fif",
    "dst_path": "neuro/data/local",
    "trans_folder": "headtrans",
    "log_folder": "log",
    "maxfilter_version": "/neuro/bin/util/mfilter",
    "MaxFilter_commands": "",
    }
}
```

Standard_settings:
- `project_name`: Name of the project
- `trans_conditions`: List of conditions to be transformed
- `trans_option`: Type of transformation (continous or initial)
- `merge_runs`: Estimate head position average over all runs if multiple
- `empty_room_files`: List of empty room files
- `sss_files`: List of SSS files
- `autobad`: Turn on or off autobad
- `badlimit`: Bad limit
- `bad_channels`: List of bad channels
- `tsss_default`: Turn on or off tSSS
- `correlation`: Correlation limit
- `movecomp_default`: Turn on or off movecomp
- `data_path`: Path to the data

Advanced_settings:
- `force`: Force maxfilter to run
- `downsample`: Downsample data
- `downsample_factor`: Downsample factor
- `apply_linefreq`: Apply line frequency filter
- `linefreq_Hz`: Line frequency in Hz
- `scripts_path`: Path to the script
- `cal`: Path to the calibration file
- `ctc`: Path to the crosstalk file
- `dst_path`: Path to the destination folder (not active yet)
- `trans_folder`: Name of the transformation folder
- `log_folder`: Name of the log folder
- `maxfilter_version`: Path to the maxfilter version
- `MaxFilter_commands`: Additional commands for maxfilter (see MaxFilter manual)

# Contributions
Improvements are welcomed. But do not change the script locally. If you need to modify this script, follow github conventions and create a new branch or fork the repository in your GitHub account to work on your version and make pull requests.