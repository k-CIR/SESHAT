# Bidsify script for NatMEG

This script converts data from NatMEG (MEG, EEG, OPM) to BIDS format.
1. The script prompts you to **select folders** for MEG/EEG data (MEG data folder), OPM data (OPM data folder), and the directory to save the BIDS-formatted data (Output data folder).
2. You will be prompted to **select** the **MEG calibration** and **cross-talk files**. If you press Cancel, the script will use the default files located at /neuro/databases/sss/ (`sss_cal.dat`) and /neuro/databases/ctc/ (`ct_sparse.fif`).
3. The script will ask if you want to **overwrite** existing files. This is important if you have already run the script with some data and only want to bidsify new data. To do this, select the same output folder containing your existing BIDS folder with the bidsified data.
4. The script checks for a **dataset description** file in the MEG folder. If not found, it will prompt you to input the necessary parameters to create one. 
5. The script checks for **participant files** in the MEG folder. If not found, it will create them with the main variables: `participant_id`, `sex`, `age`, and `group`. 
6. **Converts OPM** data to BIDS format **if** the OPM folder is **provided**. 
7. **Converts MEG** data from the selected MEG folder to BIDS format. 
8. **Generates an `error_files_list.txt` file** containing a list of files that encountered errors during the BIDS MNE function process or files that were not .fif (e.g., .txt used for specific annotations) and were therefore copied directly to the output folder.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      

### Assumptions for the code to work
- Do not use numbers in your task name when saving your raw data.  
- When applying maxFilter: Do not use underscores (`_`) in your task name. If you do, parts of the task name will be incorrectly considered as `proc` parameters for MaxFilter.

### Prerequisites
Ensure you have the following libraries installed in your Python environment: `mne`, `tkinter`, `numpy`, `pandas`, `re`, `os`, `json`, `shutil`, `glob`. <br>
The first line of this script sets the Python environment path with all necessary libraries at NatMEG.

### Location of the script at NatMEG
/Scripts/

### Running the script

To run this script, follow these steps:

1. **Make the script executable** (this step is not needed at NatMEG).  

Open a terminal, navigate to the script's directory, and run:
  ```                   
  chmod +x bidsify.py
  ```     
2. **Run the script.**  

Execute the script by running:
  ```                                
  ./bidsify.py
  ```
### Adapting the script
If you need to modify this script, do not make changes directly on the main branch. Instead, create a new branch or fork the repository in your GitHub account to work on your version.
