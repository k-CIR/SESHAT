"""
Author: C Pfeiffer & Andreas Gerhardsson (adapted from script by T Cheung)
Last Modified June 2025
Function for adding dev_to_head_trans to an OPM-MEG recording

This script performs HPI coregistration for OPM-MEG data by:
1. Localizing HPI coils in device coordinates using sequential activation
2. Computing coordinate transformations between device and head space
3. Applying transformations to MEG recordings for head localization

The pipeline processes subjects and sessions automatically, using parallel
processing for efficiency. It requires configuration files specifying
OPM parameters, HPI frequencies, and file patterns.

Dependencies:
- MNE-Python for MEG data processing
- scipy for signal processing and spatial operations
- concurrent.futures for parallel processing
- PyYAML for configuration management

Usage:
    python add_hpi.py -c config.yml
"""
import sys, getopt
import argparse
import os
import re
from glob import glob
import yaml
import numpy as np
import matplotlib.pyplot as plt
import mne

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial import Delaunay, cKDTree
import concurrent.futures
from functools import partial
from datetime import datetime

#from mne.io.pick import pick_types #use for older version of mne
from mne._fiff.pick import pick_types
from mne import Report

from scipy.signal import find_peaks

#from mne.io._digitization import _call_make_dig_points #use for older version of mne
from mne._fiff._digitization import _call_make_dig_points, _make_dig_points

from mne.transforms import (
    get_ras_to_neuromag_trans,
    Transform,
    _quat_to_affine,
    _fit_matched_points
    )

from mne.chpi import (
            _fit_coil_order_dev_head_trans,
            compute_chpi_amplitudes,
            compute_chpi_locs,
        )
from mne.io.constants import FIFF
from mne.utils import _check_fname, logger, verbose, warn
from mne.transforms import apply_trans

from utils import (
    log,
    askForConfig,
    file_contains,
    noise_patterns,
    proc_patterns
)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = f'{timestamp}_add_hpi.log'

###############################################################################
# Utility Functions
###############################################################################

def write_bw_marker_file(dsName, events, chanName, fs):
    """
    Write a BrainVision Analyzer marker file (.mrk) for MEG data analysis.
    
    Creates a marker file that contains timing information for events in a dataset,
    formatted according to BrainVision Analyzer specifications. The file includes
    metadata about the dataset and a list of event timestamps converted from samples
    to seconds using the provided sampling frequency.
    
    Parameters
    ----------
    dsName : str
        Path to the dataset directory where the marker file will be created
    events : array-like
        Array of event data where each event contains timing information in samples
    chanName : str
        Name of the channel or marker class to be written in the file
    fs : float
        Sampling frequency in Hz, used to convert sample indices to time in seconds
        
    Returns
    -------
    None
        Creates a 'MarkerFile.mrk' file in the specified dataset directory
        
    Notes
    -----
    - The marker file uses a fixed format with blue color and editable properties
    - Time values are converted from samples to seconds using the sampling frequency
    - The function assumes CLASSGROUPID of 3 and uses 1-based indexing for CLASSID
    """
    no_trigs = 1
    filepath = os.path.join(dsName, 'MarkerFile.mrk')

    with open(filepath, 'w') as fid:
        fid.write('PATH OF DATASET:\n')
        fid.write(f'{dsName}\n\n\n')
        fid.write('NUMBER OF MARKERS:\n')
        fid.write(f'{no_trigs}\n\n\n')

        for i in range(no_trigs):
            fid.write('CLASSGROUPID:\n')
            fid.write('3\n')
            fid.write('NAME:\n')
            fid.write(f'{chanName}\n')
            fid.write('COMMENT:\n\n')
            fid.write('COLOR:\n')
            fid.write('blue\n')
            fid.write('EDITABLE:\n')
            fid.write('Yes\n')
            fid.write('CLASSID:\n')
            fid.write(f'{i + 1}\n')  # Matlab uses 1-based indexing, Python uses 0-based
            fid.write('NUMBER OF SAMPLES:\n')
            fid.write(f'{len(events)}\n')
            fid.write('LIST OF SAMPLES:\n')
            fid.write('TRIAL NUMBER\t\tTIME FROM SYNC POINT (in seconds)\n')

            for t in range(len(events) - 1):
                fid.write(f'                  %+g\t\t\t\t               %+0.6f\n' % (0, events[t][0]/fs))

            fid.write(f'                  %+g\t\t\t\t               %+0.6f\n\n\n' % (0, events[t][-1]/fs))

def TC_findzerochans(info, tolerance=0.02):
    """
    Identify MEG channels with zero or invalid locations.
    
    Finds magnetometer channels positioned at the origin (0,0,0) which
    typically indicates faulty sensor positioning or missing location data.
    
    Args:
        info (mne.Info): MNE info object containing channel information
        tolerance (float): Distance tolerance in meters (default: 0.02m = 2cm)
    
    Returns:
        numpy.ndarray: Array of channel names with zero/invalid locations
        
    Note:
        Default tolerance of 2cm removes channels within sphere of origin
    """

    bads_fl=np.array([])
    picks = pick_types(info, meg='mag')
    lst = list(bads_fl)
    for j in picks:
        ch = info['chs'][j]
        if np.isclose(sum(ch['loc'][0:3]),0.,atol=1e-3).all():
            lst.append(ch['ch_name'])
    bads_fl = np.asarray(lst)
    return(bads_fl)

def tc_plot_psd(raw):
    """
    Generate power spectral density plots for MEG data quality assessment.
    
    Creates dual PSD plots (with/without projections) using Hann windowing
    for frequency domain analysis of raw MEG data.
    
    Args:
        raw (mne.io.Raw): Raw MEG data object
    
    Returns:
        tuple: (fig_proj_on, fig_proj_off) - matplotlib figure objects
        
    Side Effects:
        - Displays PSD plots with logarithmic scaling
        - Shows frequency range 0-500Hz, power range 1-10000
    """

    fname = os.path.basename(raw.filenames[0])
    n_fft = 1024
    psd_ylim = [1.,10000.]
    psd_xlim = [0.,500.]

    projs =0
    fig = raw.plot_psd(fmin=0,n_fft=n_fft,show=False, proj=True, dB=False ,xscale='log',window='hann',n_jobs=-1)
    fig3 = raw.plot_psd(fmin=0,n_fft=n_fft,show=False, proj=False, dB=False ,xscale='log',window='hann',n_jobs=-1)

    fig.suptitle('%s %d projs on hann' % (fname, projs))
    fig3.suptitle('%s projs off hann' %fname)
    fig.axes[0].set_yscale('log')
    fig3.axes[0].set_yscale('log')

    fig.axes[0].set_ylim(psd_ylim)
    fig.axes[0].set_xlim(psd_xlim)
    fig3.axes[0].set_ylim(psd_ylim)
    fig3.axes[0].set_xlim(psd_xlim)

    fig.subplots_adjust(0.1, 0.1, 0.95, 0.85)
    fig3.subplots_adjust(0.1, 0.1, 0.95, 0.85)

    plt.show()

    return(fig,fig3)

def TC_get_hpiout_names(raw):
    """
    Extract HPI output channel names and indices from raw data.
    
    Identifies miscellaneous channels containing 'out' in their names,
    which typically correspond to HPI coil output signals.
    
    Args:
        raw (mne.io.Raw): Raw data containing HPI output channels
    
    Returns:
        tuple: (hpi_names, hpi_indices)
            - hpi_names (list): Channel names containing HPI outputs
            - hpi_indices (numpy.ndarray): Corresponding channel indices
    """
    hpi_names=list()

    hpi_raw = raw.compute_psd(picks="misc")

    for name in hpi_raw.info['ch_names']:
        if 'out' in name:
            hpi_names+=[name]

    hpi_indices=np.zeros(len(hpi_names),dtype=np.int64)
    i=0
    j=0
    for ch in raw.info['ch_names']:
        for hpi in hpi_names:
            if hpi in ch:
                hpi_indices[j]=i
                j=j+1
        i=i+1


    return(hpi_names,hpi_indices)


def plot_3d(plot_params: dict, filename: str):
    """
    Create 3D visualization of sensor array, HPI coils, and digitization points.
    
    Generates interactive 3D plot showing:
    - MEG sensor positions with triangulated mesh surface
    - HPI coil locations in device coordinates (blue)
    - HPI coil locations in head coordinates (green)
    - Digitization points (black)
    
    Args:
        senspos (array): Sensor positions (Nx3)
        senslabel (array): Sensor labels
        hpipos (array): HPI positions in device coordinates
        hpilabel (array): HPI coil labels
        hpipos2 (array): HPI positions in head coordinates
        hpilabel2 (array): HPI coil labels (head coords)
        digpos (array): Digitization point positions
    
    Returns:
        None
        
    Side Effects:
        - Displays interactive 3D matplotlib plot
        - Uses Delaunay triangulation for sensor mesh
    """
    senspos = plot_params.get('senspos', None)
    senslabel = plot_params.get('senslabel', None)
    hpipos = plot_params.get('hpipos', None)
    hpilabel = plot_params.get('hpilabel', None)
    hpipos2 = plot_params.get('hpipos2', None)
    hpilabel2 = plot_params.get('hpilabel2', None)
    digpos = plot_params.get('digpos', None)
    
    # Convert lists to numpy arrays
    senspos = np.array(senspos)
    senslabel = np.array(senslabel)
    hpipos = np.array(hpipos)
    hpilabel = np.array(hpilabel)

    # Convert senspos to polar coordinates (origin = center of mass)
    center_of_mass = np.mean(senspos, axis=0)
    senspos_centered = senspos - center_of_mass
    r = np.linalg.norm(senspos_centered, axis=1)
    theta = np.arccos(senspos_centered[:, 2] / r)  # polar angle
    phi = np.arctan2(senspos_centered[:, 0], senspos_centered[:, 1])  # azimuth angle with zero on y-axis
    x_proj = theta * np.cos(phi)
    y_proj = theta * np.sin(phi)
    polar_proj = np.vstack((x_proj, y_proj)).T

    # Triangulated in 2D polar space
    tri = Delaunay(polar_proj)

    # Create a 3D plot
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # Plot the mesh
    ax.plot_trisurf(senspos[:, 0], senspos[:, 1], senspos[:, 2],
                    triangles=tri.simplices, cmap='viridis', alpha=0.6,
                    edgecolor='k', linewidth=0.2)

    # Plot the sensor positions with labels
    ax.scatter(senspos[:, 0], senspos[:, 1], senspos[:, 2], color='r', s=50)
    for i in range(len(senslabel)):
        ax.text(senspos[i, 0], senspos[i, 1], senspos[i, 2], senslabel[i], color='black', fontsize=9)

    # Plot the hpi positions with labels
    ax.scatter(hpipos[:, 0], hpipos[:, 1], hpipos[:, 2], color='b', s=100)
    for i in range(len(hpilabel)):
        ax.text(hpipos[i, 0], hpipos[i, 1], hpipos[i, 2], hpilabel[i], color='blue')

    # Plot the hpi positions with labels
    ax.scatter(hpipos2[:, 0], hpipos2[:, 1], hpipos2[:, 2], color='g', s=100)
    for i in range(len(hpilabel)):
        ax.text(hpipos2[i, 0], hpipos2[i, 1], hpipos2[i, 2], hpilabel2[i], color='green')

    # Plot the hpi positions with labels
    ax.scatter(digpos[:, 0], digpos[:, 1], digpos[:, 2], color='k', s=10)
    
    # Set viewing angle (elevation, azimuth)
    ax.view_init(elev=10, azim=20)

    #plt.show()
    fig.savefig(filename, dpi=300, bbox_inches='tight')
    
###############################################################################
# Configuration and Setup Functions
###############################################################################

def get_config(config_file: str):
    """
    Load and parse HPI processing configuration from YAML file.
    
    Extracts OPM-specific and project parameters needed for HPI coregistration
    including coil frequencies, file patterns, and processing options.
    
    Args:
        config_file (str): Path to YAML configuration file
    
    Returns:
        dict: Configuration dictionary with keys:
            - tasks: List of experimental tasks
            - polhemus_file: Pattern for Polhemus digitization files
            - opmMEG: OPM MEG data directory
            - hpinames: HPI coil naming patterns
            - hpifreq: HPI coil frequency (default: 33.0 Hz)
            - downsample_freq: Target sampling frequency (default: 1000 Hz)
            - overwrite: Whether to overwrite existing files
            - plot: Whether to generate visualization plots
    """
    
    if config_file:
        all_config = yaml.safe_load(open(config_file, 'r'))
    
    project = all_config.get('project', {})
    opm = all_config.get('opm', {})
    
    config = {
        'tasks': project.get('tasks', []),
        'polhemus_file': opm.get('polhemus', ''),
        'opmMEG': project.get('opmMEG', {}),
        'hpinames': opm.get('hpi_names', ''),
        'hpifreq': opm.get('hpi_freq', 33.0),
        'downsample_freq': opm.get('downsample_to_hz', 1000),
        'overwrite': opm.get('overwrite', False),
        'plot': opm.get('plot', False)
    }
    return config
     
def find_hpi_fit(config, subject, session, overwrite=False):
    """
    Localize HPI coils in device coordinates using sequential activation.
    
    Main HPI localization function that:
    1. Finds HPI and Polhemus files for the session
    2. Processes HPI activation signals to extract coil locations
    3. Fits magnetic dipoles to determine device coordinates
    4. Establishes coordinate transformation using fiducial points
    
    Processing Steps:
    - Loads HPI activation recording and removes bad/zero channels
    - Extracts HPI output channel signals and frequencies
    - Crops data to HPI activation windows using peak detection
    - Computes HPI amplitudes and locations for each coil
    - Uses Polhemus fiducials to establish head coordinate system
    
    Args:
        config (dict): Configuration dictionary with parameters
        subject (str): Subject identifier (e.g., 'sub-001')
        session (str): Session identifier (e.g., '20250127')
        overwrite (bool): Force reprocessing of existing files
    
    Returns:
        dict: {hedscan_files, hpi_dev, hpi_gofs, hpi_orig, hpi_names, 
                pol_info, nasion, lpa, rpa, raw, new_sfreq}
            - hedscan_files (list): Files requiring HPI transformation
            - hpi_dev (np.ndarray): HPI locations in device coordinates
            - hpi_gofs (np.ndarray): Goodness of fit for each coil (0-1)
            - hpi_orig (np.ndarray): HPI locations in head coordinates
            - hpi_names (list): HPI coil channel names
            - pol_info (mne.Info): Polhemus digitization information
            - nasion, lpa, rpa (np.ndarray): Fiducial point coordinates
            - raw (mne.io.Raw): Processed HPI data
            - new_sfreq (bool): Whether data was resampled
    
    Side Effects:
        - Logs processing steps and coil fit quality
        - Modifies raw data sampling frequency if needed
        - Removes bad and zero-location channels
    
    Notes:
        - Requires minimum 3 HPI coils for head localization
        - Uses 2-second data windows for dipole fitting
        - Peak detection finds HPI activation periods
        - Goodness of fit >0.9 indicates reliable coil localization
    """
    
    opmMEGdir = config.get('opmMEG')
    hpinames = config.get('hpinames')
    hpifreq = config.get('hpifreq', 33.0)
    new_sfreq = config.get('downsample_freq', 1000)
    hpinames=config.get('hpinames')
    exclude_patterns = [r'-\d+\.fif', '_trans', 'avg.fif']
    overwrite = config.get('overwrite', False)
    
    log_path = opmMEGdir.replace('raw', 'log')
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    # Check if all hedscan files have been processed
    all_files = sorted(glob(f'{opmMEGdir}/{subject}/{session}/hedscan/*.fif'))

    hedscan_files = [f for f in all_files if not file_contains(f, hpinames + noise_patterns + proc_patterns + exclude_patterns)]
    
    proc = 'proc-hpi+'
    if new_sfreq:
        proc += f'ds'
    proc += f'_meg'

    if not overwrite:
        hedscan_files = [f for f in hedscan_files if not os.path.exists(f.replace('raw.fif', proc + '.fif'))]
    
    
    if overwrite or hedscan_files:

        log(f"Looking for polhemus files matching: {config['polhemus_file']}", 'info',logfile=log_file, logpath=log_path)
        polfile_list = [
            file for pattern in config['polhemus_file']
            for file in glob(f"{opmMEGdir}/{subject}/{session}/triux/*{pattern}*.fif")
        ]

        polfile = polfile_list[0]
        log(f"Using: {polfile}", 'info',logfile=log_file, logpath=log_path)

        hpi_files = [f for f in all_files if file_contains(f, hpinames)]
        log(f"Looking for hpi files matching: {hpinames}", 'info',logfile=log_file, logpath=log_path)
                
        hpifile = hpi_files[0]
        log(f"Using: {hpifile}", 'info',logfile=log_file, logpath=log_path)

        raw = mne.io.read_raw_fif(hpifile)
        raw.load_data()
        #remove bad channels
        for bad_chan in raw.info["bads"]:
            raw.drop_channels(bad_chan)

        #remove zero channels
        bads=TC_findzerochans(raw.info)
        for bad_chan in bads:
            raw.drop_channels(bad_chan)
        log(f'found the following channels with locations at 0,0,0 {bads}', 'info',logfile=log_file, logpath=log_path)

        hpi_names,hpi_indices=TC_get_hpiout_names(raw)

        hpi_freqs=np.zeros(len(hpi_indices))
        for i in range(len(hpi_indices)):
            hpi_freqs[i]=hpifreq

        #resample
        if 1:
            raw.load_data().resample(1000)

        #assuming file with polhemus locations of fiducials and HPIs

        pol_info = mne.io.read_info(polfile)

        digpts=np.array([],dtype=float)
        lpa=pol_info['dig'][0]['r']
        rpa=pol_info['dig'][2]['r']
        nasion=pol_info['dig'][1]['r']

        hpi=np.array([],dtype=float)
        for j in pol_info['dig']:
            if j['kind']==2:    # FIFFV_POINT_HPI = 2
                hpi=np.append(hpi,j['r']) # to account for the gap between sensor surface and cell centre
        n=int(hpi.shape[0]/3)
        hpi=hpi.reshape((n,3))
        hpi_orig = hpi

        dev_head_t = Transform("meg", "head", trans=None)
        dev_head_t['trans']=get_ras_to_neuromag_trans(nasion, lpa, rpa) #should remain identity with the above geometry
        raw.info.update(dev_head_t=dev_head_t)

        info=raw.info

        digpts=np.array([],dtype=float)
        for j in pol_info['dig']:
            digpts=np.append(digpts,j['r']) # to account for the gap between sensor surface and cell centre
        n=int(digpts.shape[0]/3)
        digpts=digpts.reshape((n,3))

        with raw.info._unlock():
            raw.info['dig'], ctf_head_t=_call_make_dig_points(nasion, lpa, rpa, hpi[0:len(hpi_indices)], digpts, convert=True)

        sampling_freq = raw.info["sfreq"]

        start_sample =  0
        stop_sample = len(raw)

        log(f'start_sample={start_sample}, stop_sample={stop_sample}', 'info',logfile=log_file, logpath=log_path)

        hpi_locs = []

        dist_limit = 0.005

        raw_orig = raw.copy()
        slope = np.zeros((len(hpi_indices),len(pick_types(raw.info, meg='mag'))),dtype=float)

        for index in range(len(hpi_indices)):
            raw=raw_orig.copy()
            channel_index=hpi_indices[index]
            chan_name=raw.info['ch_names'][channel_index]

            msg = f'''*********HPI channel we want to localize {chan_name}**********
            channel_index = {channel_index}
            hpi_indices[index] = {hpi_indices[index]}
            '''
            log(msg, 'info',logfile=log_file, logpath=log_path)

            do_plot=False

            raw_selection = raw[channel_index, start_sample:stop_sample]
            x = raw_selection[1]
            y = raw_selection[0].T
            b = y.ravel()
            dist=round(raw.info['sfreq']/hpifreq)-2
            peaks, _ = find_peaks(b, distance=dist,height=0.0001)

            if do_plot:
                plt.plot(b)
                plt.plot(peaks, b[peaks], "x")
                plt.show()

            if len(peaks) <1 :
                log('***********Error no peaks found**********', 'error',logfile=log_file, logpath=log_path)
                exit()
                
            window=(peaks[-1]-peaks[0])/raw.info['sfreq']

            #we use this window to extract the portion of data out for the magnetic dipole fit

            minT=peaks[0]/raw.info['sfreq']
            maxT=peaks[-1]/raw.info['sfreq']

            tmin=(maxT-minT)/2.-1+minT
            tmax=(maxT-minT)/2.+1+minT #we extract 2 seconds worth of data

            msg = f'''{chan_name} first point = {peaks[0]} and last point = {peaks[-1]}, time window = {window} s
            min time = {minT}, max time = {maxT}
            tmin window = {tmin}, t max window = {tmax}
            '''
            
            log(msg, 'info',logfile=log_file, logpath=log_path)

            raw.crop(tmin=tmin,tmax=tmax)


            if do_plot:

                spectrum = raw.compute_psd(picks=hpi_indices[index],window='hann',proj=False, )
                fig=spectrum.plot(picks='misc', amplitude=True,dB=False,)

                psd_ylim = [1.,10000.]
                psd_xlim = [0.,100.]

                fig.suptitle('%s projs off hann' % (hpi_names[index]))
                fig.axes[0].set_xlim(psd_xlim)
                fig.subplots_adjust(0.1, 0.1, 0.95, 0.85)
                plt.show()

                raw_selection2 = raw[channel_index, 0:len(raw)]
                log(f'cropped time window length = {len(raw)}', 'info',logfile=log_file, logpath=log_path)
                x1 = raw_selection2[1]
                y1 = raw_selection2[0].T

                plt.plot(x1,y1)
                plt.show()


            log('************* add hpi struct to info ***********', 'info',logfile=log_file, logpath=log_path)

            hpi_sub = dict()

            hpi_sub["hpi_coils"] = []

            for _ in range(len(hpi_indices)):
                hpi_sub["hpi_coils"].append({})

            hpi_coils=[]
            for _ in range(len(hpi_indices)):
                hpi_coils.append({})

            drive_channels = hpi_names
            key_base = "Head Localization"
            default_freqs = hpi_freqs

            for i in range(len(hpi_indices)):
                # build coil structure
                hpi_coils[i]["number"] = i + 1
                hpi_coils[i]["drive_chan"] = drive_channels[i]
                log(hpi_coils[i]["drive_chan"], 'info',logfile=log_file, logpath=log_path)
                hpi_coils[i]["coil_freq"] = default_freqs[i]

                hpi_sub["hpi_coils"][i]["event_bits"] = [256]

            with raw.info._unlock():
                raw.info["hpi_subsystem"] = hpi_sub
                raw.info["hpi_meas"] = [{"hpi_coils": hpi_coils}]

            #****************************************************
            log('************* localize hpi *******************', 'info',logfile=log_file, logpath=log_path)
            n_hpis = 0

            info=raw.info

            for d in info["hpi_subsystem"]["hpi_coils"]:
                if d["event_bits"] == [256]:
                    n_hpis += 1
            if n_hpis < 3:
                warn(
                    f"{n_hpis:d} HPIs active. At least 3 needed to perform"
                    "head localization\n *NO* head localization performed"
                )
            else:
                # Localized HPIs using 2000 milliseconds of data.
                with info._unlock():
                    info["hpi_results"] = [
                        dict(
                            dig_points=[
                                dict(
                                    r=np.zeros(3),
                                    coord_frame=FIFF.FIFFV_COORD_DEVICE,
                                    ident=ii + 1,
                                )
                                for ii in range(n_hpis)
                            ],
                            coord_trans=Transform("meg", "head"),
                        )
                    ]
                raw.info["line_freq"]=None
                coil_amplitudes = compute_chpi_amplitudes(raw, tmin=0, tmax=2, t_window=2, t_step_min=2)
                slope[index,:] = coil_amplitudes['slopes'][0][index]
        #********

        assert len(coil_amplitudes["times"]) == 1
        coil_amplitudes['slopes'][0]= slope
        coil_locs = compute_chpi_locs(raw.info, coil_amplitudes)
        hpi_dev = np.array(coil_locs['rrs'][0])
        hpi_gofs = np.array(coil_locs['gofs'][0])

        log('**** Apply trans to recording file ***********************************', 'info',logfile=log_file, logpath=log_path)
    else:
        log('No files to process, all files have been processed', 'info',logfile=log_file, logpath=log_path)
        return [], None, None, None, None, None, None, None, None, None, new_sfreq
    
    hpi_fit_parameters = {
        'hedscan_files': hedscan_files,
        'hpi_dev': hpi_dev,
        'hpi_gofs': hpi_gofs,
        'hpi_orig': hpi_orig,
        'hpi_names': hpi_names,
        'pol_info': pol_info,
        'nasion': nasion,
        'lpa': lpa,
        'rpa': rpa,
        'raw': raw,
        'new_sfreq': new_sfreq
    }
    return hpi_fit_parameters

def process_single_file(datfile, hpi_fit_parameters: dict, plotResult, log_path):
    """
    Apply HPI-derived coordinate transformation to individual MEG file.
    
    Transforms a single raw MEG file from device to head coordinates using
    the HPI coil locations determined by find_hpi_fit(). Includes quality
    control and optional visualization.
    
    Processing Steps:
    1. Load raw MEG data and resample if needed
    2. Remove bad and zero-location channels
    3. Match HPI coils between device and head coordinates
    4. Compute optimal coordinate transformation
    5. Apply transformation and update file metadata
    6. Save transformed data with processing suffix
    
    Args:
        datfile (str): Path to raw MEG file to transform
        
        hpi_fit_parameters (dict): Parameters from find_hpi_fit() using:
        - hpi_dev (np.ndarray): HPI locations in device coordinates
        - hpi_gofs (np.ndarray): Goodness of fit for each HPI coil
        - hpi_orig (np.ndarray): HPI locations in head coordinates  
        - hpi_names (list): HPI coil channel names
        - pol_info (mne.Info): Polhemus digitization information
        - nasion, lpa, rpa (np.ndarray): Fiducial point coordinates
        - new_sfreq (float): Target sampling frequency
        
        plotResult (bool): Whether to generate 3D visualization
        log_path (str): Directory for log files
    
    Returns:
        None
        
    Side Effects:
        - Saves transformed file with '_proc-hpi+ds_meg.fif' suffix
        - Updates MNE info object with head coordinate system
        - Logs transformation quality metrics
        - Optionally displays 3D plot of sensor/coil positions
    
    Quality Control:
        - Only uses HPI coils with goodness of fit >0.9
        - Reports mean distance between matched coil pairs
        - Logs individual coil fit quality and status
    
    Notes:
        - Uses cKDTree for efficient HPI coil matching
        - Applies quaternion-based rigid body transformation
        - Preserves all channel types and metadata
        - File naming indicates HPI processing and downsampling
    """
    path=os.path.dirname(datfile)
    savename=os.path.basename(datfile)
    savename=os.path.splitext(savename)[0]
    savename=savename.replace('_raw','')
    
    hpi_dev = hpi_fit_parameters['hpi_dev']
    hpi_gofs = hpi_fit_parameters['hpi_gofs']
    hpi_orig = hpi_fit_parameters['hpi_orig']
    hpi_names = hpi_fit_parameters['hpi_names']
    pol_info = hpi_fit_parameters['pol_info']
    nasion = hpi_fit_parameters['nasion']
    lpa = hpi_fit_parameters['lpa']
    rpa = hpi_fit_parameters['rpa']
    new_sfreq = hpi_fit_parameters['new_sfreq']
    
    
    proc = 'proc-hpi+'
    if new_sfreq:
        proc += f'ds'
    proc += f'_meg'
        
    savename = f'{savename}_{proc}.fif'
    
    """Process a single data file"""
    raw = mne.io.read_raw_fif(datfile)

    #resample if new sampling freq different from old one
    if new_sfreq != raw.info['sfreq']: 
        raw.load_data().resample(new_sfreq)

    #remove bad channels
    for bad_chan in raw.info["bads"]:
        raw.drop_channels(bad_chan)

    #remove zero channels
    bads=TC_findzerochans(raw.info)
    for bad_chan in bads:
        raw.drop_channels(bad_chan)

    #only use good fits
    include_hpis = hpi_gofs>0.9

    tree = cKDTree(hpi_orig)
    distances, indices = tree.query(hpi_dev[include_hpis])

    log(f"hpi_orig: {hpi_dev[include_hpis]}\nhpi_dev: {hpi_orig[indices]}\n", 'info',logfile=log_file, logpath=log_path)

    trans = _quat_to_affine(_fit_matched_points(hpi_dev[include_hpis], hpi_orig[indices])[0])
    dev_to_head_trans = Transform(fro="meg", to="head", trans=trans)

    hpi_head = apply_trans(dev_to_head_trans, hpi_dev)
    dist = np.linalg.norm(hpi_orig[indices]-hpi_head[include_hpis], axis=1)

    raw.info.update(dev_head_t=dev_to_head_trans)

    info=raw.info
    digpts=np.array([],dtype=float)
    for j in pol_info['dig']:
        digpts=np.append(digpts,j['r'])
    n=int(digpts.shape[0]/3)
    digpts=digpts.reshape((n,3))

    with raw.info._unlock():
        raw.info['dig']=_make_dig_points(nasion, lpa, rpa, hpi_orig, digpts)

    raw.save(f'{path}/{savename}',overwrite=True)

    msg_coils = ''
    for index, value in enumerate(hpi_gofs):
            status = 'ok' if hpi_gofs[index]>0.9 else 'not ok'
            msg_coils += f"Coil: {hpi_names[index][-3:]}, GOF: {value:.3f}, Status: {status}\n"
    
    msg = f'''---------------------------------------------
    hpi_orig: {hpi_orig}
    hpi_dev: {hpi_dev}
    mean distance = {np.mean(dist)*1000:.1f} mm\n
    {msg_coils}
    ---------------------------------------------'''

    log(msg, 'info',logfile=log_file, logpath=log_path)

    if plotResult:
        senspos=np.array([],dtype=float)
        picks = pick_types(raw.info, meg='mag')
        for j in picks:
            senspos=np.append(senspos, apply_trans(dev_to_head_trans, (raw.info['chs'][j]['loc'][0:3])))
        n=int(senspos.shape[0]/3)
        senspos=senspos.reshape((n,3))

        senslabel=list()
        picks = pick_types(raw.info, meg='mag')
        for j in picks:
            index = raw.info['chs'][j]['ch_name'].find('s')
            if index != -1:
                senslabel.append(raw.info['chs'][j]['ch_name'][index:])
            else:
                senslabel.append('')

        digpts=np.array([],dtype=float)
        for j in raw.info['dig']:
            digpts=np.append(digpts,j['r']) # to account for the gap between sensor surface and cell centre
        n=int(digpts.shape[0]/3)
        digpts=digpts.reshape((n,3))
        hpilabel=list()
        for j in range(len(hpi_names)):
            hpilabel+=[str(j+1)]
            
        plot_params = {
            'senspos': senspos,
            'senslabel': senslabel,
            'hpipos': hpi_orig,
            'hpilabel': hpilabel,
            'hpipos2': hpi_head,
            'hpilabel2': hpi_names,
            'digpos': digpts
        }

        plot_3d(plot_params, f'{path}/{savename.replace("_meg.fif", "_3d_plot.png")}')

###############################################################################
# Command Line Interface
###############################################################################

def args_parser():
    """
    Parse command-line arguments for HPI coregistration script.
    
    Defines command-line interface with configuration file option for
    standalone script execution.
    
    Returns:
        argparse.Namespace: Parsed arguments with config file path
    """
    parser = argparse.ArgumentParser(description='Add HPI to OPM-MEG recordings.')
    parser.add_argument('-c', '--config', type=str, default='config.yml',
                        help='Path to the configuration file (default: config.yml)')
    return parser.parse_args()

def main():
    """
    Main execution function for HPI coregistration pipeline.
    
    Orchestrates the complete HPI processing workflow:
    1. Loads configuration and validates parameters
    2. Scans for subjects and sessions requiring processing
    3. Performs HPI localization for each session
    4. Applies transformations to all relevant files
    5. Uses parallel processing for efficiency
    
    Processing Pipeline:
    - Iterates through all subjects in OPM MEG directory
    - Finds sessions with 6-digit date format (YYMMDD)
    - Calls find_hpi_fit() to localize HPI coils
    - Applies transformations to hedscan files in parallel
    - Handles errors and logs processing status
    
    Configuration Requirements:
    - opmMEG: Directory containing subject/session structure
    - hpinames: Patterns to identify HPI activation files
    - polhemus_file: Patterns for Polhemus digitization files
    - hpifreq: HPI coil driving frequency
    - Processing options: overwrite, plotting, downsampling
    
    Args:
        None (uses command-line arguments or GUI config selection)
    
    Returns:
        None
        
    Side Effects:
        - Processes all eligible MEG files with HPI transformation
        - Creates log files in data/log directory
        - Uses ProcessPoolExecutor for parallel file processing
        - Prints completion status
    
    Error Handling:
        - Continues processing if individual files fail
        - Logs all exceptions for debugging
        - Validates configuration file existence
    
    Performance:
        - Parallel processing scales with available CPU cores
        - ProcessPoolExecutor handles memory-intensive operations
        - Shared parameter passing via functools.partial
    """
    args = args_parser()
    config_file = args.config
    if not config_file or not os.path.exists(config_file):
        config_file = askForConfig()
    else:
        print('No configuration file provided. Please provide a valid configuration file with -c or --config option.')
        return
    
    config = get_config(config_file)

    opmMEGdir = config.get('opmMEG')
    overwrite = config.get('overwrite', False)
    plotResult = config.get('plot', False)

    log_path = opmMEGdir.replace('raw', 'log')
    if not os.path.exists(log_path):
        os.makedirs(log_path)


    subjects = sorted([subject for subject in glob('sub-*',
                                                root_dir = f'{opmMEGdir}')
                    if os.path.isdir(f'{opmMEGdir}/{subject}')])

    for subject in subjects:

        log(f"Processing subject: {subject}", 'info',logfile=log_file, logpath=log_path)
        sessions = sorted([
            session for session in glob('*', root_dir = f'{opmMEGdir}/{subject}')
            if os.path.isdir(f'{opmMEGdir}/{subject}/{session}') and re.match(r'^\d{6}$', session)
        ])
        for session in sessions:
            
            hpi_fit_parameters = find_hpi_fit(config, subject, session, overwrite=overwrite)
            
            hedscan_files = hpi_fit_parameters.get('hedscan_files', [])
            # Create partial function with shared parameters
            if overwrite or hedscan_files:
                process_func = partial(
                    process_single_file,
                    hpi_fit_parameters=hpi_fit_parameters,
                    plotResult=plotResult,
                    log_path=log_path
                )
    
    # Use ThreadPoolExecutor or ProcessPoolExecutor

                with concurrent.futures.ProcessPoolExecutor(max_workers=len(hedscan_files)*2) as executor:
                    # Submit all tasks and get future objects
                    futures = [executor.submit(process_func, datfile) for datfile in hedscan_files]
                    
                    # Wait for all tasks to complete and handle any exceptions
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            future.result()  # This will raise an exception if the task failed
                        except Exception as exc:
                            log(f'Task generated an exception: {exc}', 'error',logfile=log_file, logpath=log_path)

# Use concurrent.futures instead of multiprocessing
if __name__ == '__main__':
    main()
    print("HPI registration completed successfully.")
    
