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

### Run script

Option 1. Run the script by executing the following command:

```bash
python bidsify.py --config=path/to/config.json
```
This will run the script with the config file wihout further questions.

Option 2. Edit config file before running the script:

```bash
python bidsify.py --config=path/to/config.json --edit
```
This will open a dialog for you to edit the config file before running the script.

Option 3. Run the script without a config flag
```bash
python bidsify.py # (add --edit to also edit an existing file)
```
You will get three options in the terminal
- `open`: Open an existing config file (default)
- `new`: Create a new config file from a default template using the dialog
- `cancel`: Cancel the operation

### Config file

```json
{
    "squidMEG": "neuro/data/sinuhe/opm",
    "opmMEG": "neuro/data/kaptah/OPMbenchmarking1",
    "BIDS": "neuro/data/local/OPM-benchmarking",
    "Calibration": "neuro/databases/sss/sss_cal.dat",
    "Crosstalk": "neuro/databases/ctc/ct_sparse.fif",
    "Dataset_description": "dataset_description.json",
    "Participants": "participants.tsv",
    "Participants mapping (csv)": "neuro/data/local/OPM-benchmarking/mapping.csv",
    "Original subjID name": "old_subject_id",
    "New subjID name": "new_subject_id",
    "Original session name": "old_session_id",
    "New session name": "new_session_id",
    "Overwrite": "on"
}
```

- `squidMEG`: Path to the raw data folder for SQUID MEG data
- `opmMEG`: Path to the raw data folder for OPM MEG data
- `BIDS`: Path to the BIDS folder where the data will be saved
- `Calibration`: Path to the calibration file
- `Crosstalk`: Path to the crosstalk file
- `Dataset_description`: Path to the dataset_description.json file
- `Participants`: Path to the participants.tsv file
- `Participants mapping (csv)`: Path to the mapping file
- `Original subjID name`: Name of the column in the mapping file that contains the original subject ID
- `New subjID name`: Name of the column in the mapping file that contains the new subject ID
- `Original session name`: Name of the column in the mapping file that contains the original session ID
- `New session name`: Name of the column in the mapping file that contains the new session ID
- `Overwrite`: If set to "on", the script will overwrite existing files in the BIDS folder

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