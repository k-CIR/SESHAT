#!/usr/bin/env python3
"""
NatMEG Pipeline Runner

This script runs the complete NatMEG preprocessing pipeline including:
- Copying data to Cerberos
- HPI coregistration
- Maxfilter processing
- BIDS conversion

Author: Andreas Gerhardsson
Date: 2025-06-26
"""

# Import necessary modules
import run_config
import copy_to_cerberos
import add_hpi
import maxfilter
import bidsify
import argparse
from os.path import exists

def args_parser():
    parser = argparse.ArgumentParser(description=
                                     '''
NatMEG Pipeline Runner
This script runs the complete NatMEG preprocessing pipeline including:
- Copying data to Cerberos
- HPI coregistration
- Maxfilter processing
- BIDS conversion                    
                                     ''',
                                     add_help=True)
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    args = parser.parse_args()
    return args

args = args_parser()
config_file = args.config
    
if not config_file or not exists(config_file):
    config = run_config.config_UI()
elif config_file:
    config = run_config.load_config(config_file)

# Copy
if config['RUN'].get('Copy to Cerberos', False):
    copy_to_cerberos.main(config)

# HPI registration
if config['RUN'].get('Add HPI coregistration', False):
    add_hpi.main(config)

# Maxfilter
if config['RUN'].get('Run Maxfilter', False):    
    mf = maxfilter.MaxFilter(config)
    mf.loop_dirs()

# Bidsification
if config['RUN'].get('Run BIDS conversion', False):
    bidsify.main(config)