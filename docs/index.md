# "SESHAT - Scripts for Extraction, Synchronisation, HPI + Analog alignment and Transfer" Documentation

SESHAT provides a comprehensive preprocessing pipeline for NatMEG MEG/EEG datasets including data preprocessing, synchronization, and reporting utilities.

## Overview

The pipeline supports:

- TRIUX/SQUID MEG data from Elekta systems
- OPM MEG data from Kaptah/OPM systems
- EEG data collected through TRIUX

Core pipeline capabilities include automated data copying, preprocessing (including MaxFilter [cli only] and HPI coregistration), server synchronization, and HTML reporting.

## Key Features

- GUI configuration interface for setting project parameters
- Automated data synchronization from acquisition computers
- HPI coregistration for OPM-MEG data using Polhemus digitization
- Batch MaxFilter processing (SSS/tSSS) [CLI only]
- Server synchronization utilities
- Interactive HTML reports summarizing processing status
- Comprehensive logging and error handling

## Documentation

- Installation: installation.md
- User Guide: user-guide/
- Configuration: configuration/
- Developer Documentation: developer/
- Reference: reference/
