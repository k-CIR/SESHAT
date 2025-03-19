# Bidsify script for NatMEG

This script converts data from NatMEG (MEG, EEG, OPM) to BIDS format and organizes the data into a BIDS-compliant folder structure. The script is designed to work with data collected at NatMEG and is based on the MNE-BIDS library.

## Prerequisits
Ensure you have the following libraries installed in your Python environment: `mne`, `mne_bids`, `tkinter`, `numpy`, `pandas`, `re`, `os`, `json`, `shutil`, `glob`

## Process
1. Make sure python modules are installed in the environment. If not, install them using the following commands:

```bash
conda install mne mne-bids
```

2. Run the script by executing the following command:
```bash
python bidsify.py --config=path/to/config.json
```
or

```bash
python bidsify.py
```

Without the --config flag, a dialog will open for you to select a configuration json file. The configuration file should contain the following fields:

```json
config_dict = {
            "squidMEG": "/neuro/sinuhe/",
            "opmMEG": "",
            "BIDS": "",
            "Calibration": "/neuro/databases/sss/sss_cal.dat",
            "Crosstalk": "/neuro/databases/ctc/ct_sparse.fif",
            "Dataset_description": "",
            "Participants": "",
            "Participants mapping file": "",
            "Original subjID": "",
            "New subjID": "",
            "Original sessionID": "",
            "New sessionID": "",
            "Overwrite": "off"  
        }
```

If a a configuration file does not exist, press cancel and a dialog will open to fill in the fields. The script will then create a configuration file for you.

3. If a `dataset_description.json` is not defined in the configuration file a dialog will open for you to fill in the necessary fields.

4. If a `participants.tsv` file is not defined in the configuration file a default one will be created.

5. The script will loop through all participants and sessions. Read all files from the raw folders, convert them to BIDS format and write locally. 

### Naming conventions
Although the script is written to handle various breaches of naming convensions, it is not yet water tight. The following naming conventions are recommended:

- Do not use numbers in your task name when saving your raw data.  
- Do not use `_` in the file-name. Tasks named `my_great_task` will be renamed to `MyGreatTask`.
- Empty room recordings should include the word `empty` or `noise` in the filename followed by `before` or `after` to indicate if it was recorded before or after the experiment.
- Resting state should be begin with `rest`, conversions for resting state names like `RS` is not yet implemented.

### Prerequisites
Ensure you have the following libraries installed in your Python environment: `mne`, `tkinter`, `numpy`, `pandas`, `re`, `os`, `json`, `shutil`, `glob`. <br>
The first line of this script sets the Python environment path with all necessary libraries at NatMEG.

### Location of the script at NatMEG
/Scripts/

### Adapting the script
Improvements are welcomed. But do not change the script locally. If you need to modify this script, follow github conventions and create a new branch or fork the repository in your GitHub account to work on your version and make pull requests.

# Maxfilter script for NatMEG

TBA