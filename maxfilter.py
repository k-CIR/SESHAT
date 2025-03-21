#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Created on Thu Jan 25 14:16:49 2024

@author: andger
"""
#%%
from glob import glob
import os
from os.path import exists, basename, dirname, isdir
import sys
import re
import tkinter as tk
from tkinter.filedialog import askdirectory, askopenfilename, asksaveasfile
import json
import mne
import subprocess


sys.path.append(os.getcwd())

from headpos import HeadPos


###############################################################################
# Global variables
###############################################################################
default_raw_path = 'neuro/data/sinuhe'
default_output_path = 'neuro/data/cerberos'

proc_patterns = ['proc', 'tsss', 'sss', 'corr', 'ds', 'mc', 'avgHead']
exclude_patterns = [r'-\d+.fif', '_trans', 'opm',  'eeg', 'avg.fif']

debug = True
###############################################################################

# TODO:
# - Read data from sinuhe, write to cerberos
# - Review and check if maxfilter configurations work
# - Integrate with Bids?
# - fix bug that don't allow you to cancel Maxfilter settings dialog and create to .json
#   Now, to create a new file cancel and then load next time.
# DONE:
# - Maxfilter version selectable in advance settings


def file_contains(file: str, pattern: list):
    return bool(re.compile('|'.join(pattern)).search(file))

class set_parameter:
    def __init__(self, mxf, mne_mxf, string):
        self.mxf = mxf
        self.mne_mxf = mne_mxf
        self.string = string

class MaxFilter:
    
    def __init__(self, **kwargs):

        self.set_maxfilter_parameters()

        try:

            with open(self.json_name, 'r') as f:
                maxfilter_parameters_dict = json.load(f)
            std = maxfilter_parameters_dict['standard_settings']
            adv = maxfilter_parameters_dict['advanced_settings']
            
            # self.parameters = std | adv
            parameters = std.copy()
            parameters.update(adv)
            
            self.parameters = parameters

            self.data_root = f"{self.parameters['data_path']}/{self.parameters['project_name']}"
            self.scripts_path = os.getcwd()

            # self.maxfilter_path = '/neuro/bin/util/maxfilter'
            self.maxfilter_path = self.parameters.get('maxfilter_version')
            print(self.maxfilter_path)

        except FileNotFoundError:
            print('No MaxFilter settings file selected')

    
    def set_maxfilter_parameters(self):

        """
        Behind the scenes:
            Creates a json-file, or open an existing one with maxfilter parameters
        In the GUI:
            Make your changes and save to create or update the json-file
        
        Parameters
        ----------
        
        json_name : string
            Define the name of the file to use
        
        Returns
        -------
            A json-file to use with run_maxfilter.py
        
        """

        self.data_path = askdirectory(title='Select project for MEG data', initialdir=default_raw_path)  # shows dialog box and return the MEG path
        print("The folder selected for MEG data is %s." % str(self.data_path))
        data_root = dirname(self.data_path)
        
        if not self.data_path:
            print('No data folder selected. Exiting...')
            sys.exit(1)

        self.json_name = askopenfilename(title='Select Maxfilter settings', initialdir=self.data_path, filetypes=[('Json File', '*.json')])  # shows dialog box and return the MEG path

        if not self.json_name:
            self.json_name='maxfilter_parameter.json'

            data = {
                'standard_settings': {
                    ## STEP 1: On which conditions should average headposition be done (consistent naming is mandatory!)?
                    'project_name': basename(self.data_path),
                    'trans_conditions': ['task1', 'task2'],
                    'trans_option': 'mne_continous', # mne_continous, continous or initial
                    'trans_type': 'mean',
                    'merge_runs': 'on',

                    ## STEP 2: Put the names of your empty room files (files in this array won't have "movecomp" applied) (no commas between files and leave spaces between first and last brackets)
                    'empty_room_files': ['empty_room_before.fif', 'empty_room_after.fif'],
                    'sss_files': ['empty_room_before.fif', 'empty_room_after.fif'],

                    ## STEP 3: Select MaxFilter options (advanced options)
                    'autobad': 'on',
                    'badlimit': 7,
                    'bad_channels':[''],
                    'tsss_default': 'on',
                    'correlation': 0.98,
                    'movecomp_default': 'on',
                    'data_path': data_root
                },

                'advanced_settings': {
                    # 'trans': 'off',
                    # 'transformation_to': 'default',
                    # 'headpos': 'off',
                    'force': 'off',
                    'downsample': 'off',
                    'downsample_factor': 4,
                    'apply_linefreq': 'off',
                    'linefreq_Hz': 50,
                    'scripts_path': '/home/natmeg/Scripts',
                    'cal': '/neuro/databases/sss/sss_cal.dat',
                    'ctc': '/neuro/databases/ctc/ct_sparse.fif',
                    'dst_path': 'NatMEG',
                    'trans_folder': 'headtrans',
                    'log_folder': 'log',
                    'maxfilter_version': ['/neuro/bin/util/mfilter', '/neuro/bin/util/maxfilter'],
                    'MaxFilter_commands': '',
            }
                }

        # if not exists(json_name):
        #     with open(json_name, 'w') as output_file:
        #             json.dump(data, output_file, indent=4, default=list)
        else:
            print(f'{self.json_name} exists, loading dict...')
            
            with open(self.json_name, 'r') as f:
                data = json.load(f)

        standard_settings = data['standard_settings']
        advanced_settings = data['advanced_settings']

        # %% 
        # # Create main window
        root = tk.Tk()
        root.eval('tk::PlaceWindow . center')

        # Set window title
        root.title("MaxFilter settings")

        # Create standard settings section
        std_frame = tk.LabelFrame(root, text="Standard Settings", padx=20, pady=20, border=2)
        std_frame.grid(row=0, column=0,
                    ipadx=5, ipady=5, sticky='ns')

        std_new = {k: v for k, v in standard_settings.items()}
        std_chb = {}
        
        std_labels = []
        std_entries = []
        # Add labels and entries for standard settings
        for i, key in enumerate(standard_settings):
            value = standard_settings[key]
            std_labels.append(key)

            if key == 'trans_option':
                label = tk.Label(std_frame, text=key)
                label.grid(row=i, column=0, sticky="e",
                        padx=2, pady=2)
                
                selected_option = tk.StringVar()
                options = ['mne_continous', 'continous', 'initial']
                entry = tk.OptionMenu(std_frame, selected_option, *options)
                entry.grid(row=i, column=1, padx=2, pady=2, sticky="w")
                selected_option.set(options[0])
                
                std_entries.append(selected_option)

            elif value in ['on', 'off']:
                label = tk.Label(std_frame, text=key)
                label.grid(row=i, column=0, sticky="e",
                        padx=2, pady=2)

                std_chb[key] = tk.StringVar()
                std_chb[key].set(value)

                check_box = tk.Checkbutton(std_frame,
                                        variable=std_chb[key],
                                        onvalue='on', offvalue='off', 
                                        text='')

                check_box.grid(row=i, column=1,
                            padx=2, pady=2, sticky='w')
                std_entries.append(std_chb[key])
                
            else:
                label = tk.Label(std_frame, text=key)
                label.grid(row=i, column=0, sticky="e",
                        padx=2, pady=2)
                entry = tk.Entry(std_frame, width=40)
            
                if isinstance(value, list):
                    value = ', '.join(value)
                entry.insert(0, value)
                entry.grid(row=i, column=1, padx=2, pady=2)
                std_entries.append(entry)

        
        
        # Create advanced settings section
        adv_frame = tk.LabelFrame(root, text="Advanced Settings", padx=20, pady=20, border=2)

        adv_new = {k: v for k, v in advanced_settings.items()}
        adv_chb = {}

        adv_labels = []
        adv_entries = []
        # Add labels and entries for advanced settings
        for i, key in enumerate(advanced_settings):
            value = advanced_settings[key]
            adv_labels.append(key)

            if key == 'maxfilter_version':
                label = tk.Label(adv_frame, text=key)
                label.grid(row=i, column=0, sticky="e",
                        padx=2, pady=2)
                
                selected_option = tk.StringVar()
                # options = ['mfilter (3.0)', 'maxfilter (2.2)']
                # TODO: FIx this!
                # options = [adv_new['maxfilter_version'].values()]
                options = ['/neuro/bin/util/mfilter', '/neuro/bin/util/maxfilter']
                entry = tk.OptionMenu(adv_frame, selected_option, *options)
                entry.grid(row=i, column=1, padx=2, pady=2, sticky="w")

                # option_select = '/neuro/bin/util/' + options[0].split(' (')[0]
                option_select = options[0]

                selected_option.set(option_select)
                
                adv_entries.append(selected_option)

            elif value in ['on', 'off']:
                label = tk.Label(adv_frame, text=key)
                label.grid(row=i, column=0, sticky="e", padx=2, pady=2)
                
                adv_chb[key] = tk.StringVar()
                adv_chb[key].set(value)
                check_box = tk.Checkbutton(adv_frame,
                                        variable=adv_chb[key], onvalue='on', offvalue='off',
                                        text='')

                check_box.grid(row=i, column=1, padx=2, pady=2, sticky='w')
                adv_entries.append(adv_chb[key])
                
            else:
                label = tk.Label(adv_frame, text=key)
                label.grid(row=i, column=0, sticky="e", padx=2, pady=2)
                entry = tk.Entry(adv_frame, width=40)
            
                if isinstance(value, list):
                    value = ', '.join(value)
                entry.insert(0, value)
                entry.grid(row=i, column=1, padx=2, pady=2)
                adv_entries.append(entry)

        # Buttons frame
        button_frame = tk.LabelFrame(root, text="", padx=10, pady=10, border=0)

        button_frame.grid(row=1, column=0, columnspan=3, sticky='nsew', padx=5, pady=5)
        
        # def update_name(*args):
        #     standard_settings['']
        #     first_name = first_name_var.get()
        #     last_name = last_name_var.get()
        #     f"proc-{}.fif"
            
        #     full_name.set(f"{first_name}{last_name}")
        
        # # Create a variable to store the full name
        # full_name = tk.StringVar()

        # # Create and position the name label
        # name_label = tk.Label(root, textvariable=full_name)
        # name_label.grid(row=len(standard_settings) + 1,
        #                 columnspan=2)
        
        # first_name_var.trace("w", update_name)
        # last_name_var.trace("w", update_name)

        def toggle_advanced():
            if adv_frame.winfo_ismapped():
                adv_frame.grid_forget()
                toggle_button.config(text="Show Advanced Settings")
            else:
                # button_frame.pack(fill="both", expand=True)
                adv_frame.grid(row=0, column=1,
                            ipadx=5, ipady=5, sticky='ns')
                toggle_button.config(text="Hide Advanced Settings")

        def cancel():
            root.destroy()
            print('Closed')

        def save():
            data = {'standard_settings': {},
                    'advanced_settings': {}}

            for key, entry in zip(std_labels, std_entries):
                if ', ' in entry.get():
                    data['standard_settings'][key] = [x.strip() for x in entry.get().split(', ') if x.strip()]
                else:
                    data['standard_settings'][key] = entry.get()

            for key, entry in zip(adv_labels, adv_entries):
                
                if ', ' in entry.get():
                    data['advanced_settings'][key] = [x.strip() for x in entry.get().split(', ') if x.strip()]
                else:
                    data['advanced_settings'][key] = entry.get()
                
            # Replace with save data and store in project folder
            json_path = f'{self.data_path}/{self.json_name}'

            save_json_name = asksaveasfile(initialdir=self.data_path, filetypes=[('Json File', '*.json')], defaultextension='.json')
            json.dump(data, save_json_name, indent=4, default=list)

            # with open(save_json_name, 'w') as output_file:
            #     json.dump(data, output_file, indent=4, default=list)
            root.destroy()
            print(f'Saving maxfilter parameters to {self.json_name}')
            # print('Run MaxFilter') 
            # run_maxfilter(data)

        save_button = tk.Button(button_frame,
                                text="Save", command=save)
        # toggle_button.pack(side='right', pady=10)
        save_button.grid(row=0, column=0)

        # Create button to toggle advanced settings visibility
        toggle_button = tk.Button(button_frame,
                                text="Show Advanced Settings", command=toggle_advanced)

        # toggle_button.pack(side='left', pady=10)
        toggle_button.grid(row=0, column=1)

        cancel_button = tk.Button(button_frame,
                                text="Cancel", command=cancel)
        # toggle_button.pack(side='right', pady=10)
        cancel_button.grid(row=0, column=2)


        # Start GUI loop
        root.mainloop()
        # return(data)

    def set_params(self, subject, session, task):
        """_summary_

        Args:
            subject (str): _description_
            task (str): _description_
        """
        for k, v in self.parameters.items():
            setattr(self, k, v)

        self.subject = subject
        self.session = session
        self.task = task
        self.path = f'{self.data_root}/{self.subject}/{self.session}/meg'
        trans_file = f'{self.path}/{self.trans_folder}/{self.task}_trans.fif'
        self.trans_name = trans_file
        self.trans_process_file=True

        def set_trans(trans_name):
            if 'continous' in self.trans_option and self.task in self.trans_conditions:
                if trans_name:
                    mxf = '-trans %s' % trans_name
                    mne_mxf = '--trans=%s' % trans_name
                    string = 'trans'
            # elif 'initial' in self.trans_option or \
            #         any([p in mf.task for p in mf.empty_room_files]):
            #     self.trans_process_file=False
            #     mxf=''
            #     mne_mxf = ''
            #     string = ''
            else:
                self.trans_process_file=False
                mxf=''
                mne_mxf = ''
                string = ''
                print('No information about trans')
                #sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.trans_ = set_trans(self.trans_name)

        # create set_force function
        def set_force():
            if self.force == 'on':
                mxf = '-force'
            elif self.force == 'off':
                mxf = ''
            else:
                print('faulty "force" setting (must be on or off)')
                sys.exit(1)
            return(mxf)
        self.force_ = set_force()
        
        def set_cal():
            if self.cal:
                mxf = '-cal %s' % self.cal
                mne_mxf = '--calibration=%s' % self.cal
                string = 'cal_'
            else:
                print('no "cal" file found')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.cal_ = set_cal()
        
        def set_ctc():
            if self.ctc:
                mxf = '-ctc %s' % self.ctc
                mne_mxf = '--cross_talk=%s' % self.ctc
                string = 'ctc_'
            else:
                print('no "ctc" file found')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.ctc_ = set_ctc()
        
        # create set_mc function (sets movecomp according to wishes above and abort if set incorrectly, this is a function such that it can be changed throughout the script if empty_room files are found) 
        def set_mc():
            if self.movecomp_default == 'on':
                mxf = '-movecomp'
                mne_mxf = '--movecomp'
                string='mc'
            elif self.movecomp_default == 'off':
                mxf = ''
                mne_mxf = ''
                string = ''
            else:
                print('faulty "movecomp" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.mc_ = set_mc()
        
        # create set_tsss function
        def set_tsss():
            if self.tsss_default == 'on':
                mxf = '-st'
                mne_mxf='--st'
                string='tsss'
            elif self.tsss_default == 'off':
                mxf = ''
                mne_mxf=''
                string=''
            else:
                print('faulty "tsss" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf,mne_mxf, string))
        self.tsss_ = set_tsss()
        
        # create set_ds function
        def set_ds():
            if self.downsample == 'on':
                if int(self.downsample_factor) > 1:
                    mxf = '-ds %s' % self.downsample_factor
                    mne_mxf = ''
                    string = 'dsfactor-%s_' % \
                        self.downsample_factor
                else:
                    print('downsampling factor must be an INTEGER greater than 1')
            elif self.downsample == 'off':
                mxf = ''
                mne_mxf = ''
                string=''
            else:
                print('faulty "downsampling" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.ds_ = set_ds()
    
        def set_corr():
            if self.correlation:
                mxf = '-corr %s' % self.correlation
                mne_mxf = '--corr=%s' % self.correlation
                string = 'corr %s_' % \
                    round(float(self.correlation)*100)
            elif not self.correlation:
                mxf = ''
                mne_mxf= ''
                string=''
            else:
                print('faulty "correlation" setting (must be between 0 and 1)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.corr_ = set_corr()
        # set linefreq according to wishes above and abort if set incorrectly
        def set_linefreq():
            if self.apply_linefreq == 'on':
                mxf = '-linefreq %s' % self.linefreq_Hz
                mne_mxf = '--linefreq %s' % self.linefreq_Hz
                string = 'linefreq-%s_' % self.linefreq_Hz
            elif self.apply_linefreq == 'off':
                mxf = ''
                mne_mxf = ''
                string = ''
            else:
                print('faulty "apply_linefreq" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.linefreq_ = set_linefreq()
        
        # Set autobad parameters
        def set_autobad():
            if self.autobad == 'on':
                mxf = '-autobad %s' % self.autobad
                mne_mxf = '--autobad=%s' % self.badlimit
                string = 'autobad_%s' % self.autobad
            elif self.autobad == 'off':
                mxf = '-autobad %s' % self.autobad
                mxf = '--autobad %s' % self.autobad
                string = ''
            else:
                print('faulty "autobad" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.autobad_ = set_autobad()
        
        def set_bad_limit():
            if self.autobad == 'on':
                mxf = '-badlimit %s' % self.badlimit
                mne_mxf = ''
                string=''
            elif self.autobad == 'off':
                mxf = ''
                mne_mxf= ''
                string=''
            else:
                print('faulty "badlimit" setting (must be on)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.badlimit_ = set_bad_limit()
        
        def set_bad_channels():
            if self.bad_channels:
                if isinstance(self.bad_channels, list):
                    bad_ch = ' '.join(self.bad_channels)
                else:
                    bad_ch = self.bad_channels
                mxf = '-bad %s' % bad_ch
                mne_mxf = '--bad %s' % bad_ch
                string = '_bad_%s' % bad_ch
            elif not self.bad_channels:
                mxf = ''
                mne_mxf= ''
                string=''
            else:
                print('faulty "bad_channels" setting (must be comma separated list)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        self.bad_channels_ = set_bad_channels()
        
        # If empty room file set tsss off and remove trans and headpos
        if 'noise' in self.task or 'empty' in self.task:
            self.tsss_default = 'off'
            self.movecomp_default = 'off'
            self.tsss_.mxf = ''
            self.tsss_.mne_mxf = ''
            self.tsss_.string = ''
            self.mc_.mxf = ''
            self.mc_.mne_mxf = ''
            self.mc_.string = ''
            self.corr_.mxf = ''
            self.corr_.mne_mxf = ''
            self.corr_.string = ''
        if self.task in self.sss_files:
            self.tsss_default = 'off'

        def set_bids_proc():
            proc = []
            if self.tsss_default == 'on':
                proc.append(self.tsss_.string)
                if self.correlation:
                    proc.append(f'corr{round(float(self.correlation)*100)}')
            else:
                proc.append('sss')

            if self.movecomp_default == 'on':
                proc.append(self.mc_.string)
            
            if self.trans_process_file:
                proc.append('avgHead')

            
        
            return('+'.join(proc))

        self.proc = set_bids_proc()
    
    def run_command(self, subject, session):

        subj_path = f'{self.data_root}/{subject}/{session}/meg'
        # Change directory to subj_path
        os.chdir(subj_path)

        # Create log directory if it doesn't exist
        os.makedirs(self.parameters['log_folder'], exist_ok=True)

        # List all files in directory
        all_fifs = sorted(glob('*.fif'))
        
        
        file_contains()
        pattern = re.compile(r'|'.join(patterns))

        naming_convs = [
            'raw',
            'meg'
        ]
        naming_conv = re.compile(r'|'.join(naming_convs))

        trans_condition = self.parameters['trans_conditions']
        sss_files = self.parameters['sss_files']
        empty_room_files = self.parameters['empty_room_files']

        if isinstance(trans_condition, str):
            trans_condition = [trans_condition]
        if isinstance(sss_files, str):
            sss_files = [sss_files]
        if isinstance(empty_room_files, str):
            empty_room_files = [empty_room_files]

        tasks_to_run = sorted(list(set(
            trans_condition +
            sss_files +
            empty_room_files)))
        
        self.additional_cmd = self.parameters['MaxFilter_commands']

        merge_runs = self.parameters['merge_runs']

        # TODO: Nice print of all files to run
        # files = [f for f in all_fifs if task in f and not pattern.search(f.lower())]

        # print_files = '\n'.join(files)
        
        # print(f'Running Maxfilter on:
        #           {print_files}')

        for task in tasks_to_run:
            
            self.set_params(subject, session, task)

            files = [f for f in all_fifs if task in f and not pattern.search(f.lower())]

            # TODO: Fix file merge. Need to create temp raw names or separate maxfilter folder
            if merge_runs == 'on' and len(files) > 1:
                print('Merging files...')

                os.makedirs('bkp', exist_ok=True)
                
                raws_sorted = sorted([mne.io.read_raw_fif(
                f,
                preload=False,
                allow_maxshield=True, verbose='error') for f in files],
                        key=lambda x: x.info['meas_date'])
                try:
                    raw = mne.concatenate_raws(raws_sorted)
                except ValueError:
                    raws_sorted[0].info['dev_head_t'] = raws_sorted[1].info['dev_head_t']
                    raw = mne.concatenate_raws(raws_sorted)
                
                raw.load_data()
                # Move files to bkp
                for rfname in raw._filenames:
                    os.rename(rfname, rfname.replace('/meg', '/meg/bkp'))

                raw.save(raw._filenames[0])
            
            all_fifs = sorted(glob('*.fif'))

            
            for file in files:


                clean = file.replace('.fif', f'_proc-{self.proc}.fif')
                ncov = naming_conv.search(clean)
                
                if not ncov:
                    clean = clean.replace('.fif', '_meg.fif')

                # TODO: Check if bids-naming can be implemented here
                
                if not exists(clean):
                    print('''
                          Running Maxfilter on
                          Subject: %s
                          Session: %s
                          Task: %s
                          ''' % (self.subject, 
                                 self.session,
                                 file))

                    if self.trans_process_file:
                        os.makedirs(self.trans_folder, exist_ok=True)
                        hp = HeadPos(self.data_root)
                        hp.create_avg_transfile(subj_path, file)

                    log = f'{self.log_folder}/{clean.replace(".fif",".log")}'

                    command_list = []
                    command_list.extend([
                        self.maxfilter_path,
                        '-f %s' % file,
                        '-o %s' % clean,
                        self.cal_.mxf,
                        self.ctc_.mxf,
                        self.trans_.mxf,
                        self.tsss_.mxf,
                        self.ds_.mxf,
                        self.corr_.mxf,
                        self.mc_.mxf,
                        self.autobad_.mxf,
                        self.badlimit_.mxf,
                        self.bad_channels_.mxf,
                        self.linefreq_.mxf,
                        self.force_,
                        self.additional_cmd,
                        '-v',
                        '| tee -a %s' % log
                        ])
                    self.command_mxf = ' '.join(command_list)
                    self.command_mxf = re.sub(r'\\s+', ' ', self.command_mxf).strip()
                    print(self.command_mxf)
                    
                    if not debug:
                        subprocess.call(self.command_mxf, shell=True, cwd=subj_path)
                    else:
                        print(self.command_mxf)

                else:
                    print('''
                          Existing file: %s
                          Delete to rerun MaxFilter process
                          ''' % clean)
        os.chdir(self.scripts_path)
        #subprocess.run(f'cd {self.scripts_path}')

    def loop_dirs(self):
        """Iterates over the subject and session directories and maxfilter.

        This method loops through the subject and session directories in the specified data root directory.
        It performs specific tasks on the files found in each directory.

        Returns:
            None
        """
        subjects = sorted(glob('NatMEG*',
                               root_dir=self.data_root))
        # TODO: List dir to only include folders
        for subject in subjects:

            # sessions = sorted([f for f in glob('*', root_dir=f'{self.data_root}/{subject}') if isdir(f)])
            sessions = sorted(glob('*', root_dir=f'{self.data_root}/{subject}'))
            print(sessions)

            sessions = [s for s in sessions if isdir(f'{self.data_root}/{subject}/{s}')]

            for session in sessions:
                self.run_command(subject, session)

# %%
def main():
    
    mf = MaxFilter()
    mf.loop_dirs()


if __name__ == "__main__":
    main()