#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Nov 16 15:06:45 2023

@author: andger
"""
# %%
import mne
import os
from os.path import basename, dirname
import re
from os.path import exists
from glob import glob
#    from mne.chpi import read_head_pos, head_pos_to_trans_rot_t
from mne.transforms import (invert_transform,
                            read_trans, write_trans)
from mne.preprocessing import compute_average_dev_head_t
from mne.chpi import (compute_chpi_amplitudes, compute_chpi_locs,
                      head_pos_to_trans_rot_t, compute_head_pos,
                      write_head_pos,
                      read_head_pos)
import matplotlib.patches as mpatches

# %%

class HeadPos:
    def __init__(self, data_path='.', out_path=None):
        if not out_path:
            out_path = data_path
        self.data_path = data_path
        self.out_path = out_path

    def create_avg_transfile(self, subj_path, file, overwrite=False):
        
        data_path = self.data_path
        out_path = self.out_path

        trans_path = subj_path.replace(data_path, out_path) + '/headtrans'
        os.makedirs(trans_path, exist_ok=True)

        trans_name = f"{trans_path}/{file.replace('.fif', '_trans.fif')}"
        headpos_name = trans_name.replace('_trans.fif', '_headpos.pos')
        
        if overwrite or not exists(headpos_name):

            

            raw = mne.io.read_raw_fif(f'{subj_path}/{file}', allow_maxshield=True)

            # TODO: Check if hpi are recorder otherwise revert to initial head position

            chpi_amplitudes = compute_chpi_amplitudes(raw)
            chpi_locs = compute_chpi_locs(raw.info, chpi_amplitudes)
            head_pos = compute_head_pos(raw.info, chpi_locs, verbose=True)
            write_head_pos(headpos_name, head_pos)
            print("Wrote headposition file to:\n%s" 
                  % headpos_name.split('/')[-1])
            
            if not exists(trans_name):

                head_pos = read_head_pos(headpos_name)
                trans, rot, t = head_pos_to_trans_rot_t(head_pos) 
            
                mean_trans = invert_transform(
                    compute_average_dev_head_t(raw, head_pos))

            # Write trans file
            try:
                write_trans(trans_name, mean_trans, overwrite=overwrite)
                print("Wrote trans file to\n%s" %
                    trans_name.split('/')[-1])
            except FileExistsError:
                print("%s already exists" % trans_name.split('/')[-1])

     # Plot summary with MNE plot fun
     # TODO: Update plot function and add as default to main
    def plot_movement(self, subj_path, file, overwrite=False):
        
        if not out_path:
            out_path = data_path
        
        data_path = self.data_path

        trans_path = subj_path.replace(data_path, out_path) + 'headtrans'
       
        trans_name = f"{trans_path}/{file.replace('.fif', '_trans.fif')}"
        headpos_name = trans_name.replace('_trans.fif', '_headpos.pos')

        # Read info from, if multiple sort by recording time
        info = mne.io.read_info(f'{subj_path}/{file}')
        head_pos = read_head_pos(headpos_name)
        avg_trans = read_trans(trans_name)
        original_head_dev_t = invert_transform(info["dev_head_t"])
        
        """
        Plot trances of movement for insepction. Uses mne.viz.plot_head_positions
        """
        fig = mne.viz.plot_head_positions(head_pos, mode='traces', show=False)
        red_patch = mpatches.Patch(color='r', label='Original')
        blue_patch = mpatches.Patch(color='g', label='Average')

        for ax, ori, av in zip(fig.axes[::2],
                               original_head_dev_t['trans'][:3, 3],
                               avg_trans['trans'][:3, 3]):
            ax.axhline(1000*ori, color="r")
            ax.axhline(1000*av, color="g")
            
        fig.legend(handles=[red_patch, blue_patch], loc='upper left')
        fig.tight_layout()
        return(fig)
