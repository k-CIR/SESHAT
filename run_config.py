import yaml
import json
import sys
import argparse
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.filedialog import asksaveasfile, askopenfile

default_path = 'neuro/data/local/'

def create_default_config():
    config = {
        'project': {
            'name': '',
            'InstitutionName': 'Karolinska Institutet',
            'InstitutionAddress': 'Nobels vag 9, 171 77, Stockholm, Sweden',
            'InstitutionDepartmentName': 'Department of Clinical Neuroscience (CNS)',
            'description': 'project for MEG data',
            'tasks': [''],
            'squidMEG': 'neuro/data/local/',
            'opmMEG': 'neuro/data/local/',
            'BIDS': 'neuro/data/local/',
            'Calibration': 'neuro/databases/sss/sss_cal.dat',
            'Crosstalk': 'neuro/databases/ctc/ct_sparse.fif'
        },
        'opm': {
            'polhemus': [''],
            'hpi_names': ['HPIpre', 'HPIpost', 'HPIbefore', 'HPIafter'],
            'frequency': 33,
            'downsample_to_hz': 1000,
            'overwrite': False,
            'plot': False
        },
        'maxfilter': {
            'standard_settings': {
                'trans_conditions': [''],
                'trans_option': 'continous',
                'merge_runs': True,
                'empty_room_files': ['empty_room_before.fif', 'empty_room_after.fif'],
                'sss_files': '',
                'autobad': True,
                'badlimit': '7',
                'bad_channels': '',
                'tsss_default': True,
                'correlation': '0.98',
                'movecomp_default': True,
                'subjects_to_skip': ''
            },
            'advanced_settings': {
                'force': False,
                'downsample': False,
                'downsample_factor': '4',
                'apply_linefreq': False,
                'linefreq_Hz': '50',
                'maxfilter_version': '/neuro/bin/util/maxfilter',
                'MaxFilter_commands': ''
            }
        },
        'bids': {
            'Dataset_description': 'dataset_description.json',
            'Participants': 'participants.tsv',
            'Participants_mapping_file': 'participant_mapping_example.csv',
            'Original_subjID_name': 'old_subject_id',
            'New_subjID_name': 'new_subject_id',
            'Original_session_name': 'old_session_id',
            'New_session_name': 'new_session_id',
            'Overwrite': False
        }
    }
    return config

def save_config(config, filename='config.yaml'):
    save_path = asksaveasfile(defaultextension=".yml", filetypes=[("YAML files", ["*.yml", "*.yaml"]), ("JSON files", '*.json')], initialdir=default_path)
    
    if save_path:
        if save_path.name.endswith('.yml') or save_path.name.endswith('.yaml'):
            with open(save_path.name, 'w') as file:
                yaml.dump(config, file, default_flow_style=False, sort_keys=False)
        elif save_path.name.endswith('.json'):
            with open(save_path.name, 'w') as file:
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
    option = input("Do you want to open an existing config file or create a new? ([open]/new/cancel): ").strip().lower()
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
    root.title("NatMEG Config Editor")
    root.geometry("700x750")
    
    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=False, padx=3, pady=3)
    
    # Project tab
    project_frame = ttk.Frame(notebook)
    notebook.add(project_frame, text="Project")
    
    # Create scrollable frame for project
    # project_canvas = tk.Canvas(project_frame)
    # project_scrollbar = ttk.Scrollbar(project_frame, orient="vertical", command=project_canvas.yview)
    # project_scrollable_frame = ttk.Frame(project_canvas)
    
    # project_scrollable_frame.bind(
    #     "<Configure>",
    #     lambda e: project_canvas.configure(scrollregion=project_canvas.bbox("all"))
    # )
    
    # project_canvas.create_window((0, 0), window=project_scrollable_frame, anchor="nw")
    # project_canvas.configure(yscrollcommand=project_scrollbar.set)
    
    project_vars = {}
    row = 0
    for key, value in config['project'].items():
        ttk.Label(project_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        if key == 'tasks':
            var = tk.StringVar(value=', '.join(value) if isinstance(value, list) else str(value))
            widget = ttk.Entry(project_frame, textvariable=var, width=50)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(project_frame, textvariable=var, width=50, justify='left')

        project_vars[key] = var
        widget.grid(row=row, column=1, padx=3, pady=1)
        row += 1
    
    # project_canvas.pack(side="left", fill="both", expand=True)
    # project_scrollbar.pack(side="right", fill="y")
    
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
    
    # MaxFilter tab
    maxfilter_frame = ttk.Frame(notebook)
    notebook.add(maxfilter_frame, text="MaxFilter")
    
    maxfilter_vars = {'standard_settings': {}, 'advanced_settings': {}}
    
    # Standard settings frame
    standard_frame = ttk.LabelFrame(maxfilter_frame, text="Standard Settings", padding="10")
    standard_frame.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
    
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
        maxfilter_vars['standard_settings'][key] = var
        widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
        row += 1
    
    # Advanced settings frame
    advanced_frame = ttk.LabelFrame(maxfilter_frame, text="Advanced Settings", padding="10")
    advanced_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=5)
    
    row = 0
    for key, value in config['maxfilter']['advanced_settings'].items():
        ttk.Label(advanced_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            widget = ttk.Checkbutton(advanced_frame, variable=var)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(advanced_frame, textvariable=var, width=50)
        maxfilter_vars['advanced_settings'][key] = var
        widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
        row += 1
    
    # BIDS tab
    bids_frame = ttk.Frame(notebook)
    notebook.add(bids_frame, text="BIDS")
    
    bids_vars = {}
    row = 0
    for key, value in config['bids'].items():
        ttk.Label(bids_frame, text=key + ":").grid(row=row, column=0, sticky='w', padx=3, pady=1)
        if isinstance(value, bool):
            var = tk.BooleanVar(value=value)
            widget = ttk.Checkbutton(bids_frame, variable=var)
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(bids_frame, textvariable=var, width=50)
        bids_vars[key] = var
        widget.grid(row=row, column=1, padx=3, pady=1, sticky='w')
        row += 1
    
    def save():
        # Update config with GUI values
        for key, var in project_vars.items():
            config['project'][key] = var.get()
        for key, var in opm_vars.items():
            config['opm'][key] = var.get()
        for section in ['standard_settings', 'advanced_settings']:
            for key, var in maxfilter_vars[section].items():
                config['maxfilter'][section][key] = var.get()
        for key, var in bids_vars.items():
            config['bids'][key] = var.get()

        save_config(config)
        root.destroy()
    
    def cancel():
        root.destroy()
        sys.exit(0)
    
    # Cancel button
    cancel_button = ttk.Button(root, text="Cancel", command=cancel)
    cancel_button.pack(side='right', padx=20, pady=1) 
    
    # Save button
    save_button = ttk.Button(root, text="Save Configuration", command=save)
    save_button.pack(side='left', padx=20, pady=1)
    
    root.mainloop()

def args_parser():

    parser = argparse.ArgumentParser(description="Create or edit NatMEG configuration file.", add_help=True)
    
    parser.add_argument('--config', type=str, help="Path to the configuration file to use", default=None)
    
    return parser.parse_args()

if __name__ == "__main__":
    args = args_parser()
    config_file = args.config
    if not config_file:
        config_file = askForConfig()
        if config_file == 'new':
            config_file = None

    config_UI(config_file)
        