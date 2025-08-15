import yaml
import json
import sys
import os
from os.path import exists
import argparse
import tkinter as tk
from tkinter import ttk
from tkinter.filedialog import asksaveasfile, askopenfile
import threading
import subprocess
from tkinter.scrolledtext import ScrolledText

default_path = '/neuro/data/local/'

global config

def create_default_config():
    
    config = {
        'RUN': {
            'Copy to Cerberos': True,
            'Add HPI coregistration': True,
            'Run Maxfilter': True,
            'Run BIDS conversion': True,
            'Sync to CIR': True
        },
        'project': {
            'name': '',
            'CIR-ID': '',
            'InstitutionName': 'Karolinska Institutet',
            'InstitutionAddress': 'Nobels vag 9, 171 77, Stockholm, Sweden',
            'InstitutionDepartmentName': 'Department of Clinical Neuroscience (CNS)',
            'description': 'project for MEG data',
            'tasks': [''],
            'sinuhe_raw': '/neuro/data/sinuhe',
            'kaptah_raw': '/neuro/data/kaptah',
            'squidMEG': default_path,
            'opmMEG': default_path,
            'BIDS': default_path,
            'Calibration': '/neuro/databases/sss/sss_cal.dat',
            'Crosstalk': '/neuro/databases/ctc/ct_sparse.fif',
        },
        'opm': {
            'polhemus': [''],
            'hpi_names': ['HPIpre', 'HPIpost', 'HPIbefore', 'HPIafter'],
            'frequency': 33,
            'downsample_to_hz': 1000,
            'overwrite': False,
            'plot': False,
        },
        'maxfilter': {
            'standard_settings': {
                'trans_conditions': [''],
                'trans_option': 'continous',
                'merge_runs': True,
                'empty_room_files': ['empty_room_before.fif', 'empty_room_after.fif'],
                'sss_files': [''],
                'autobad': True,
                'badlimit': '7',
                'bad_channels': [''],
                'tsss_default': True,
                'correlation': '0.98',
                'movecomp_default': True,
                'subjects_to_skip': ['']
            },
            'advanced_settings': {
                'force': False,
                'downsample': False,
                'downsample_factor': '4',
                'apply_linefreq': False,
                'linefreq_Hz': '50',
                'maxfilter_version': '/neuro/bin/util/maxfilter',
                'MaxFilter_commands': '',
                'debug': False
            }
        },
        'bids': {
            'Dataset_description': 'dataset_description.json',
            'Participants': 'participants.tsv',
            'Participants_mapping_file': 'participant_mapping_example.csv',
            'Conversion_file': 'bids_conversion.tsv',
            'Overwrite_conversion': False,
            'Original_subjID_name': 'old_subject_id',
            'New_subjID_name': 'new_subject_id',
            'Original_session_name': 'old_session_id',
            'New_session_name': 'new_session_id',
            'overwrite': False,
            'dataset_type': 'raw',
            'data_license': '',
            'authors': '',
            'acknowledgements': '',
            'how_to_acknowledge': '',
            'funding': '',
            'ethics_approvals': '',
            'references_and_links': '',
            'doi': 'doi:<insert_doi>'
                }
    }
    return config

def save_config(config, filename=None):
    if filename:
        save_path = filename
    elif filename is None:
        save_path = asksaveasfile(defaultextension=".yml", filetypes=[("YAML files", ["*.yml", "*.yaml"]), ("JSON files", '*.json')], initialdir=default_path)
        save_path = save_path.name if save_path else None

    if save_path:
        if save_path.endswith('.yml') or save_path.endswith('.yaml'):
            with open(save_path, 'w') as file:
                yaml.dump(config, file, default_flow_style=False, sort_keys=False)
        elif save_path.endswith('.json'):
            with open(save_path, 'w') as file:
                json.dump(config, file, indent=4)

def load_config(config_file=None):
    if not config_file:
        config_file = askopenfile(filetypes=[("YAML files", ["*.yml", "*.yaml"]), ("JSON files", '*.json')], initialdir=default_path)
    if config_file:
        if hasattr(config_file, 'name'):
            filename = config_file.name
        else:
            filename = config_file
        
        if filename.endswith('.yml') or filename.endswith('.yaml'):
            with open(filename, 'r') as file:
                config = yaml.safe_load(file)
        elif filename.endswith('.json'):
            with open(filename, 'r') as file:
                config = json.load(file)
    # Strings to lists
    if config:
        config['project']['tasks'] = config['project']['tasks'].split(',') if isinstance(config['project']['tasks'], str) else config['project']['tasks']
        config['opm']['hpi_names'] = config['opm']['hpi_names'].split(',') if isinstance(config['opm']['hpi_names'], str) else config['opm']['hpi_names']
        config['opm']['polhemus'] = config['opm']['polhemus'].split(',') if isinstance(config['opm']['polhemus'], str) else config['opm']['polhemus']
        config['maxfilter']['standard_settings']['trans_conditions'] = config['maxfilter']['standard_settings']['trans_conditions'].split(',') if isinstance(config['maxfilter']['standard_settings']['trans_conditions'], str) else config['maxfilter']['standard_settings']['trans_conditions']
        config['maxfilter']['standard_settings']['sss_files'] = config['maxfilter']['standard_settings']['sss_files'].split(',') if isinstance(config['maxfilter']['standard_settings']['sss_files'], str) else config['maxfilter']['standard_settings']['sss_files']
        config['maxfilter']['standard_settings']['empty_room_files'] = config['maxfilter']['standard_settings']['empty_room_files'].split(',') if isinstance(config['maxfilter']['standard_settings']['empty_room_files'], str) else config['maxfilter']['standard_settings']['empty_room_files']
        config['maxfilter']['standard_settings']['subjects_to_skip'] = config['maxfilter']['standard_settings']['subjects_to_skip'].split(',') if isinstance(config['maxfilter']['standard_settings']['subjects_to_skip'], str) else config['maxfilter']['standard_settings']['subjects_to_skip']
        config['maxfilter']['standard_settings']['bad_channels'] = config['maxfilter']['standard_settings']['bad_channels'].split(',') if isinstance(config['maxfilter']['standard_settings']['bad_channels'], str) else config['maxfilter']['standard_settings']['bad_channels']

    return config
    

def askForConfig():
    """_summary_

    Args:
        file_config (str, optional): _description_. Defaults
            to None.

    Returns:
        dict: dictionary with the configuration parameters
    """
    option = input("Do you want to open an existing config file or create a new? ([open]/new/cancel): ").lower().strip()


    # Check if the file is defined or ask for it
    if option not in ['o', 'open']:
        if option in ['n', 'new']:
            return 'new'
        elif option in ['c', 'cancel']:
            print('User cancelled')
            sys.exit(1)

    else:
        config_file = askopenfile(
            title='Select config file',
            filetypes=[('YAML files', ['*.yml', '*.yaml']), ('JSON files', '*.json')],
            initialdir=default_path)

        if not config_file:
            print('No configuration file selected. Exiting opening dialog')
            sys.exit(1)
        
        print(f'{config_file.name} selected')
        return config_file

def config_UI(config_file=None):
    
    if config_file:
        config = load_config(config_file)
    
    else:
        config = create_default_config()
    
    root = tk.Tk()
    root.title(f"NatMEG Config Editor")
    
    root.geometry("700x800")
    
    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=False, padx=3, pady=3)
    
    style = ttk.Style()
    style.map("C.TButton", foreground=[('disabled', 'grey')])
    
    # Project tab
    project_frame = ttk.Frame(notebook)
    notebook.add(project_frame, text="Project")
    
    # Create notebook for Project sub-tabs
    project_notebook = ttk.Notebook(project_frame)
    project_notebook.pack(fill='both', expand=True, padx=3, pady=3)
    
    # Standard settings tab
    project_standard_frame = ttk.Frame(project_notebook)
    project_notebook.add(project_standard_frame, text="Standard Settings")
    
    # Advanced settings tab
    project_advanced_frame = ttk.Frame(project_notebook)
    project_notebook.add(project_advanced_frame, text="Advanced Settings")
    
    project_vars = {}
    
    # Standard project settings
    standard_keys = ['name', 'CIR-ID', 'description', 'tasks',
                     'sinuhe_raw', 'kaptah_raw']
    row = 0
    for key in standard_keys:
        value = config['project'][key]
        ttk.Label(project_standard_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        if key == 'tasks':
            var = tk.StringVar(value=', '.join(value) if isinstance(value, list) else str(value))
            widget = ttk.Entry(project_standard_frame, textvariable=var, width=50)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(project_standard_frame, textvariable=var, width=50, justify='left')
        project_vars[key] = var
        widget.grid(row=row, column=1, padx=3, pady=1)
        row += 1
        
    # Project information frame (in standard tab)
    project_std_info_frame = ttk.Frame(project_standard_frame)
    project_std_info_frame.grid(row=row, column=0, columnspan=2, padx=3, pady=3, sticky='ew')
    
    # Add informational text about the Project tab
    std_info_text = """
This tab allows you to set the basic project information and paths for the project.

• name: Name of project directory on local disk
• CIR-ID: CIR ID of the project, used for data management
• description: Brief description of the project
• tasks: Comma-separated list in square brackets of experimental tasks (e.g. [rest, oddball, memory])
• sinuhe_raw: Path to Sinuhe raw data directory
• kaptah_raw: Path to Kaptah raw data directory
"""

    std_info_label = ttk.Label(project_std_info_frame, text=std_info_text, 
                          justify='left', wraplength=650, 
                          font=('TkDefaultFont', 11))
    std_info_label.pack(anchor='w', padx=5, pady=5)
    
    # Advanced project settings
    advanced_keys = ['InstitutionName',
                     'InstitutionAddress', 'InstitutionDepartmentName', 
                      'squidMEG', 'opmMEG', 'BIDS', 'Calibration', 'Crosstalk']
    row = 0
    for key in advanced_keys:
        value = config['project'][key]
        # Update paths with project name
        if key in ['squidMEG', 'opmMEG', 'BIDS'] and config['project']['name']:
            project_name = config['project']['name']
            if project_name not in value:  # Only update if not already updated with project name
                if key == 'BIDS':
                    value = f"{value}{project_name}/BIDS"
                else:
                    value = f"{value}{project_name}/raw"
        ttk.Label(project_advanced_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        var = tk.StringVar(value=str(value))
        widget = ttk.Entry(project_advanced_frame, textvariable=var, width=50, justify='left')
        project_vars[key] = var
        widget.grid(row=row, column=1, padx=3, pady=1)
        
        # Update paths immediately when project name changes
        if key in ['squidMEG', 'opmMEG', 'BIDS', 'sinuhe_raw', 'kaptah_raw']:
            def update_path(name_var, path_var, path_type):
                def callback(*args):
                    name = name_var.get()
                    base_path = default_path
                    if path_type == 'BIDS':
                        path_var.set(f"{base_path}{name}/BIDS" if name else base_path)
                    elif path_type in ['squidMEG', 'opmMEG']:
                        path_var.set(f"{base_path}{name}/raw" if name else base_path)
                    elif path_type in ['sinuhe_raw', 'kaptah_raw']:
                        path_var.set(f"{base_path}{name}" if name else base_path)
                return callback
            project_vars['name'].trace('w', update_path(project_vars['name'], var, key))
        
        row += 1
    
    # Project information frame (in advanced tab)
    project_adv_info_frame = ttk.Frame(project_advanced_frame)
    project_adv_info_frame.grid(row=row, column=0, columnspan=2, padx=3, pady=3, sticky='ew')
    
    # Add informational text about the Project tab
    adv_info_text = """


• InstitutionName: Name of the institution
• InstitutionAddress: Address of the institution
• InstitutionDepartmentName: Department name
• squidMEG: Path to directory for SquidMEG data
• opmMEG: Path to directory for OPM data
• BIDS: Path to directory for BIDS data
• Calibration: Path to SSS calibration file
• Crosstalk: Path to SSS crosstalk file
"""

    adv_info_label = ttk.Label(project_adv_info_frame, text=adv_info_text, 
                          justify='left', wraplength=650, 
                          font=('TkDefaultFont', 11))
    adv_info_label.pack(anchor='w', padx=5, pady=5)
    
    # OPM tab
    opm_frame = ttk.Frame(notebook)
    notebook.add(opm_frame, text="OPM")
    
    opm_vars = {}
    row = 0
    for key, value in config['opm'].items():
        ttk.Label(opm_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            widget = ttk.Checkbutton(opm_frame, variable=var, onvalue=True, offvalue=False)
        elif key == 'hpi_names' or key == 'polhemus':
            var = tk.StringVar(value=', '.join(value) if isinstance(value, list) else str(value))
            widget = ttk.Entry(opm_frame, textvariable=var, width=50)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(opm_frame, textvariable=var, width=50)
        opm_vars[key] = var
        widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
        row += 1
        
    # OPM information frame (in standard tab)
    opm_info_frame = ttk.Frame(opm_frame)
    opm_info_frame.grid(row=row, column=0, columnspan=2, padx=3, pady=3, sticky='ew')
    
    # Add informational text about the OPM tab
    opm_info_text = """
Set the parameters for adding HPI coregistration polhemus data from the TRIUX recording, to the OPM data.

• polhemus: name(s) of fif-file(s) with Polhemus coregistration data
• hpi_names: Comma-separated list in square brackets of names of HPI recording, only one will be used(e.g. [HPIpre, HPIpost, HPIbefore, HPIafter]). 
• frequency: Frequency of the HPI in Hz
• downsample_to_hz: Downsample OPM data to this frequency
• overwrite: Overwrite existing OPM data files
• plot: Store a plot of the OPM data after processing
"""

    opm_info_label = ttk.Label(opm_info_frame, text=opm_info_text, 
                          justify='left', wraplength=650, 
                          font=('TkDefaultFont', 11))
    opm_info_label.pack(anchor='w', padx=5, pady=5)
    
    # MaxFilter tab
    maxfilter_frame = ttk.Frame(notebook)
    notebook.add(maxfilter_frame, text="MaxFilter")
    
    maxfilter_vars = {'standard_settings': {}, 'advanced_settings': {}}
    
    # Create notebook for MaxFilter sub-tabs
    maxfilter_notebook = ttk.Notebook(maxfilter_frame)
    maxfilter_notebook.pack(fill='both', expand=True, padx=3, pady=3)
    
    # Standard settings tab
    standard_frame = ttk.Frame(maxfilter_notebook)
    maxfilter_notebook.add(standard_frame, text="Standard Settings")
    
    row = 0
    for key, value in config['maxfilter']['standard_settings'].items():
        ttk.Label(standard_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            widget = ttk.Checkbutton(standard_frame, variable=var)
        elif key == 'trans_conditions' or key == 'empty_room_files' or key == 'subjects_to_skip' or key == 'bad_channels' or key == 'sss_files':
            var = tk.StringVar(value=', '.join(value) if isinstance(value, list) else str(value))
            widget = ttk.Entry(standard_frame, textvariable=var, width=50)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(standard_frame, textvariable=var, width=50)
            if key == 'trans_option':
                selected_option = tk.StringVar()
                options = [value] + list(
                {'continous', 'initial'} - {value})
                widget = tk.OptionMenu(standard_frame, selected_option, *options)
                selected_option.set(options[0])
                var = selected_option
        maxfilter_vars['standard_settings'][key] = var
        widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
        row += 1
    
    # Maxfilter information frame (in standard tab)
    mf_std_info_frame = ttk.Frame(standard_frame)
    mf_std_info_frame.grid(row=row, column=0, columnspan=2, padx=3, pady=3, sticky='ew')
    
    # Add informational text about the Project tab
    mf_std_info_text = """
Set the parameters for MaxFilter processing.

• trans_conditions: Comma-separated list in square brackets tasks which should be transformed to average head (e.g. [rest, oddball, memory])
• trans_option: Option for transformation, either 'continous' for average or 'inital' for initial head position
• merge_runs: Use multiple runs to calculate average head position, and apply on all runs (files themselves are not merged)
• empty_room_files: Comma-separated list in square brackets of empty room files to use for MaxFilter processing (e.g. [empty_room_before.fif, empty_room_after.fif])
• sss_files: tasks which should only be sss filtered (e.g. [rest])
• autobad: Automatically detect and exclude bad channels
• badlimit: Bad channel threshold for processing
• bad_channels: Comma-separated list in square brackets of bad channels to exclude from processing (e.g. [MEG0111, MEG0112])
• tsss_default: Use default TSSS settings
• correlation: Correlation threshold for TSSS, e.g. '0.98'
• movecomp_default: Use default movecomp settings
• subjects_to_skip: Comma-separated list in square brackets of subject IDs to skip during MaxFilter processing (e.g. [1234, 4321])


"""
    mf_std_info_label = ttk.Label(mf_std_info_frame, text=mf_std_info_text, 
                          justify='left', wraplength=550, 
                          font=('TkDefaultFont', 10))
    mf_std_info_label.pack(anchor='w', padx=5, pady=0)
    
    # Advanced settings tab
    advanced_frame = ttk.Frame(maxfilter_notebook)
    maxfilter_notebook.add(advanced_frame, text="Advanced Settings")
    
    row = 0
    for key, value in config['maxfilter']['advanced_settings'].items():
        ttk.Label(advanced_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            widget = ttk.Checkbutton(advanced_frame, variable=var)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(advanced_frame, textvariable=var, width=50)
            if key == 'maxfilter_version':
                selected_option = tk.StringVar()
                options = [value] + list(
                {'/neuro/bin/util/maxfilter', '/neuro/bin/util/mfilter'} - {value})
                options = [value] + list(
                {'/neuro/bin/util/maxfilter', '/neuro/bin/util/mfilter'} - {value})
                widget = tk.OptionMenu(advanced_frame, selected_option, *options)
                selected_option.set(options[0])
                var = selected_option
                
        maxfilter_vars['advanced_settings'][key] = var
        widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
        row += 1
    
    # Maxfilter information frame (in advanced tab)
    mf_adv_info_frame = ttk.Frame(advanced_frame)
    mf_adv_info_frame.grid(row=row, column=0, columnspan=2, padx=3, pady=3, sticky='ew')
    
    # Add informational text about the Project tab
    mf_adv_info_text = """
Set the parameters for MaxFilter processing.

• force: Force MaxFilter to run even if badchannels are detected
• downsample: Downsample data
• downsample_factor: Factor to downsample data by
• apply_linefreq: Apply line frequency filtering
• linefreq_Hz: Line frequency in Hz to apply filtering
• maxfilter_version: Path to MaxFilter executable
• MaxFilter_commands: Additional MaxFilter commands to run, e.g. '-v' for verbose output
• debug: Enable debug mode for MaxFilter (if true will print command instead of running it, headpos will still be applied)

"""
    mf_adv_info_label = ttk.Label(mf_adv_info_frame, text=mf_adv_info_text, 
                          justify='left', wraplength=550, 
                          font=('TkDefaultFont', 10))
    mf_adv_info_label.pack(anchor='w', padx=5, pady=0)
    
    # BIDS tab
    bids_frame = ttk.Frame(notebook)
    notebook.add(bids_frame, text="BIDS")
    
    # Create notebook for BIDS sub-tabs
    bids_notebook = ttk.Notebook(bids_frame)
    bids_notebook.pack(fill='both', expand=True, padx=3, pady=3)
    
    # Standard settings tab
    bids_standard_frame = ttk.Frame(bids_notebook)
    bids_notebook.add(bids_standard_frame, text="Standard Settings")
    
    bids_vars = {}
    
    # Standard BIDS settings (matching default config keys)
    standard_bids_keys = ['Dataset_description', 'Participants',
                          'Participants_mapping_file', 'Conversion_file','Overwrite_conversion',
                          'Original_subjID_name', 'New_subjID_name', 'Original_session_name', 
                          'New_session_name', 'overwrite']
    
    row = 0
    for key in standard_bids_keys:
        if key in config['bids']:
            value = config['bids'][key]
            ttk.Label(bids_standard_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
            if isinstance(value, bool):
                var = tk.BooleanVar(value=value)
                widget = ttk.Checkbutton(bids_standard_frame, variable=var)
            else:
                var = tk.StringVar(value=str(value))
                widget = ttk.Entry(bids_standard_frame, textvariable=var, width=50)
            bids_vars[key] = var
            widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
            row += 1
    
    # BIDS information frame (in standard tab)
    bids_info_frame = ttk.Frame(bids_standard_frame)
    bids_info_frame.grid(row=row, column=0, columnspan=2, padx=3, pady=3, sticky='ew')
    
    # Add informational text about the BIDS standard tab
    bids_info_text = """
Set the parameters for Bidsification.

• Dataset_description: Path to dataset_description.json file
• Participants: Path to participants.tsv file
• Participants_mapping_file: Path to participant mapping CSV file
• Conversion_file: Path to conversion file (e.g. bids_conversion.tsv)
• Overwrite_conversion: Overwrite existing conversion files
• Original_subjID_name: Name of the original subject ID column in the mapping file
• New_subjID_name: Name of the new subject ID column in the mapping file
• Original_session_name: Name of the original session ID column in the mapping file
• New_session_name: Name of the new session ID column in the mapping file
• overwrite: Overwrite existing BIDS files

"""
    
    bids_info_label = ttk.Label(bids_info_frame, text=bids_info_text, 
                          justify='left', wraplength=550, 
                          font=('TkDefaultFont', 10))
    bids_info_label.pack(anchor='w', padx=5, pady=0)
    
    # Dataset description tab
    bids_dataset_frame = ttk.Frame(bids_notebook)
    bids_notebook.add(bids_dataset_frame, text="Dataset Description")
    
    # Dataset description settings (matching default config keys)
    dataset_bids_keys = ['dataset_type', 'data_license', 'authors', 'acknowledgements', 'how_to_acknowledge', 
                        'funding', 'ethics_approvals', 'references_and_links', 'doi']
    
    row = 0
    for key in dataset_bids_keys:
        if key in config['bids']:
            value = config['bids'][key]
            ttk.Label(bids_dataset_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
            if isinstance(value, bool):
                var = tk.BooleanVar(value=value)
                widget = ttk.Checkbutton(bids_dataset_frame, variable=var)
            else:
                var = tk.StringVar(value=str(value))
                widget = ttk.Entry(bids_dataset_frame, textvariable=var, width=50)
            bids_vars[key] = var
            widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
            row += 1
    
    # Dataset description information frame
    dataset_info_frame = ttk.Frame(bids_dataset_frame)
    dataset_info_frame.grid(row=row, column=0, columnspan=2, padx=3, pady=3, sticky='ew')
    
    # Add informational text about the dataset description tab
    dataset_info_text = """
Set the dataset description metadata for BIDS.

• dataset_type: Type of dataset (e.g., 'raw', 'derivative')
• data_license: License under which the data is made available
• authors: List of individuals who contributed to the creation/curation of the dataset
• acknowledgements: Text acknowledging contributions
• how_to_acknowledge: Instructions on how researchers should acknowledge this dataset
• funding: List of sources of funding
• ethics_approvals: List of ethics committee approvals
• references_and_links: List of references, publications, and links
• doi: Digital Object Identifier of the dataset

"""
    
    dataset_info_label = ttk.Label(dataset_info_frame, text=dataset_info_text, 
                          justify='left', wraplength=550, 
                          font=('TkDefaultFont', 10))
    dataset_info_label.pack(anchor='w', padx=5, pady=0)
    
    # Run tab
    run_frame = ttk.Frame(notebook)
    notebook.add(run_frame, text="RUN")
    
    run_vars = {}
    row = 0
    for key, value in config['RUN'].items():
        ttk.Label(run_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        var = tk.BooleanVar(value=value)
        widget = ttk.Checkbutton(run_frame, variable=var)
        run_vars[key] = var
        widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
        row += 1
    
    terminal_frame = ttk.Frame(root)
    terminal_output = ScrolledText(terminal_frame, height=18, width=90, state='disabled', font=('TkDefaultFont', 10))
    terminal_output.pack(fill='both', expand=True, padx=5, pady=5)
    def show_terminal():
        terminal_frame.pack(side='top', fill='both', expand=True, padx=10, pady=5)
    def hide_terminal():
        terminal_frame.pack_forget()

    # Execute button
    def execute():
        # Update config with current GUI values
        for key, var in run_vars.items():
            config['RUN'][key] = var.get()
        # Always use the latest config_file value
        config_path = config_file if config_file else None
        cmd = ['python', 'natmeg_pipeline.py', 'run']
        if config_path:
            cmd += ['--config', config_path]
        # Show terminal output window
        show_terminal()
        terminal_output.config(state='normal')
        terminal_output.delete('1.0', 'end')
        terminal_output.insert('end', f"Running: {' '.join(cmd)}\n\n")
        terminal_output.config(state='disabled')
        root.update()
        def run_subprocess():
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=os.environ)
            for line in process.stdout:
                terminal_output.config(state='normal')
                terminal_output.insert('end', line)
                terminal_output.see('end')
                terminal_output.config(state='disabled')
                root.update()
            process.wait()
            terminal_output.config(state='normal')
            if process.returncode == 0:
                terminal_output.insert('end', '\nPipeline finished successfully.')
            else:
                terminal_output.insert('end', f'\nPipeline exited with code {process.returncode}.')
            terminal_output.config(state='disabled')
            root.update()
        threading.Thread(target=run_subprocess, daemon=True).start()
    
    # Execute button widget (initially disabled until a save occurs)
    execute_button = ttk.Button(run_frame, text="Save to execute", command=execute, state='disabled', style='C.TButton')
    execute_button.grid(row=row, column=0, columnspan=2, pady=20, padx=10, sticky='ew')
    
    def save():
        # Disable save button
        save_button.config(state='disabled', text='Saved!', 
                           style='C.TButton')
        
        # Enable execute button when config is saved
        execute_button.config(state='normal', text='Execute')
        
        # Update config with GUI values
        for key, var in project_vars.items():
            value = var.get()
            if key == 'tasks':
                # Convert comma-separated string to list, remove blanks
                config['project'][key] = [item.strip() for item in value.split(',') if item.strip()]
            else:
                config['project'][key] = value
    
        for key, var in opm_vars.items():
            value = var.get()
            if key in ['hpi_names', 'polhemus']:
                # Convert comma-separated string to list, remove blanks
                config['opm'][key] = [item.strip() for item in value.split(',') if item.strip()]
            else:
                config['opm'][key] = value
    
        for section in ['standard_settings', 'advanced_settings']:
            for key, var in maxfilter_vars[section].items():
                value = var.get()
                if key in ['trans_conditions', 'empty_room_files', 'subjects_to_skip', 'bad_channels', 'sss_files']:
                    # Convert comma-separated string to list, remove blanks
                    config['maxfilter'][section][key] = [item.strip() for item in value.split(',') if item.strip()]
                else:
                    config['maxfilter'][section][key] = value
    
        for key, var in bids_vars.items():
            config['bids'][key] = var.get()
    
        for key, var in run_vars.items():
            config['RUN'][key] = var.get()

        save_config(config, filename=config_file if config_file else None)
        
        # Switch to RUN tab
        notebook.select(run_frame)
        
        # Re-enable save button after any variable changes
        def enable_save_button(*args):
            save_button.config(state='normal', text='Save')
            # Disable execute button when changes are made
            execute_button.config(state='disabled', text='Save to execute', style='C.TButton')
        
        # Bind to all variables to detect changes
        for var in project_vars.values():
            var.trace('w', enable_save_button)
        for var in opm_vars.values():
            var.trace('w', enable_save_button)
        for section_vars in maxfilter_vars.values():
            for var in section_vars.values():
                var.trace('w', enable_save_button)
        for var in bids_vars.values():
            var.trace('w', enable_save_button)
        for var in run_vars.values():
            var.trace('w', enable_save_button)

    def save_as():
        # Update config with GUI values (same as save function)
        for key, var in project_vars.items():
            value = var.get()
            if key == 'tasks':
                config['project'][key] = [item.strip() for item in value.split(',') if item.strip()]
            else:
                config['project'][key] = value
    
        for key, var in opm_vars.items():
            value = var.get()
            if key in ['hpi_names', 'polhemus']:
                config['opm'][key] = [item.strip() for item in value.split(',') if item.strip()]
            else:
                config['opm'][key] = value
    
        for section in ['standard_settings', 'advanced_settings']:
            for key, var in maxfilter_vars[section].items():
                value = var.get()
                if key in ['trans_conditions', 'empty_room_files', 'subjects_to_skip', 'bad_channels', 'sss_files']:
                    config['maxfilter'][section][key] = [item.strip() for item in value.split(',') if item.strip()]
                else:
                    config['maxfilter'][section][key] = value
    
        for key, var in bids_vars.items():
            config['bids'][key] = var.get()
    
        for key, var in run_vars.items():
            config['RUN'][key] = var.get()

        # Force file dialog for save as (pass None as filename)
        save_config(config, filename=None)
    
    def open_config():
        new_config_file = askopenfile(
            title='Select config file',
            filetypes=[('YAML files', ['*.yml', '*.yaml']), ('JSON files', '*.json')],
            initialdir=default_path)
        nonlocal config_file
        if new_config_file:
            # Load the new configuration
            new_config = load_config(new_config_file)
            if new_config:
                # Update all GUI variables with new config values
                for key, var in project_vars.items():
                    if key in new_config['project']:
                        if key == 'tasks':
                            var.set(', '.join(new_config['project'][key]) if isinstance(new_config['project'][key], list) else str(new_config['project'][key]))
                        else:
                            var.set(str(new_config['project'][key]))
                for key, var in opm_vars.items():
                    if key in new_config['opm']:
                        if key in ['hpi_names', 'polhemus']:
                            var.set(', '.join(new_config['opm'][key]) if isinstance(new_config['opm'][key], list) else str(new_config['opm'][key]))
                        else:
                            var.set(new_config['opm'][key])
                for section in ['standard_settings', 'advanced_settings']:
                    for key, var in maxfilter_vars[section].items():
                        if key in new_config['maxfilter'][section]:
                            if key in ['trans_conditions', 'empty_room_files', 'subjects_to_skip', 'bad_channels', 'sss_files']:
                                var.set(', '.join(new_config['maxfilter'][section][key]) if isinstance(new_config['maxfilter'][section][key], list) else str(new_config['maxfilter'][section][key]))
                            else:
                                var.set(new_config['maxfilter'][section][key])
                for key, var in bids_vars.items():
                    if key in new_config['bids']:
                        var.set(new_config['bids'][key])
                for key, var in run_vars.items():
                    if key in new_config['RUN']:
                        var.set(new_config['RUN'][key])
                # Update the global config variable
                nonlocal config
                config = new_config
                # Update config_file to the newly loaded file
                if hasattr(new_config_file, 'name'):
                    config_file = new_config_file.name
                else:
                    config_file = new_config_file
                # Update the loaded file label
                loaded_file_label.config(text=f"Loaded config file: {config_file}", foreground='blue')
    
    def cancel():
        root.destroy()
        sys.exit(0)
        config = None
    
    # Show loaded config file above buttons
    if config_file:
        loaded_file_label = ttk.Label(root,
            text=f"Loaded config file: {config_file}",
            font=('TkDefaultFont', 10, 'bold'), foreground='blue')
        loaded_file_label.pack(side='bottom', fill='x', padx=10, pady=2)
    else:
        loaded_file_label = ttk.Label(root,
            text="No config file loaded (using default)",
            font=('TkDefaultFont', 10, 'bold'), foreground='gray')
        loaded_file_label.pack(side='bottom', fill='x', padx=10, pady=2)

    # Button frame at bottom
    button_frame = ttk.Frame(root)
    button_frame.pack(side='bottom', fill='x', padx=10, pady=5)
    # Cancel button
    cancel_button = ttk.Button(button_frame, text="Cancel", command=cancel)
    cancel_button.pack(side='right', padx=5)
    
    # Save as button
    save_as_button = ttk.Button(button_frame, text="Save as...", command=save_as)
    save_as_button.pack(side='right', padx=5)
    
    # Save button
    save_button = ttk.Button(button_frame, text="Save", command=save)
    save_button.pack(side='right', padx=5)
    
    # Open button
    open_button = ttk.Button(button_frame, text="Open", command=open_config)
    open_button.pack(side='right', padx=5)
    
    # Center the window on screen
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    # Bring window to front and focus
    root.lift()
    root.attributes('-topmost', True)
    root.after(10, lambda: root.attributes('-topmost', False))
    root.focus_force()
    
    root.mainloop()
    return config

def args_parser():
    parser = argparse.ArgumentParser(description=
                                     '''
Configuration script for NatMEG pipeline.
                                     
This script allows you to create or edit a configuration file for the NatMEG pipeline.
You can specify paths, settings, and options for various stages of the pipeline including MaxFilter,
OPM processing, and BIDS conversion. The configuration can be saved in YAML or JSON format.
You can also provide a path to an existing configuration file to load its settings.
                                     
                                     ''',
                                     add_help=True,
                                     usage='maxfilter [-h] [-c CONFIG]')
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    args = parser.parse_args()
    return args

def main(config_file=None):
    args = args_parser()
    
    config_file = args.config
    
    if not config_file or not exists(config_file):
        config = config_UI()
    elif config_file:
        config = config_UI(config_file)
        return config

if __name__ == "__main__":
    main()