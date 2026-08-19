# Pipeline Stages

The SESHAT pipeline processes MEG/EEG data through several stages controlled by the `RUN` section of the config file.

## 1. copy_raw — Data Copy

Raw data are copied from acquisition computers (SQUID/OPM systems) to a central processing machine. This step ensures consistent project structure and data availability.

Config key: `RUN.copy_raw`

## 2. opm_preprocess — OPM Preprocessing

For OPM-MEG recordings, head position indicator (HPI) information is added using Polhemus digitization data, and analog channels are renamed.

Config key: `RUN.opm_preprocess`

## (3) MaxFilter Processing (Legacy, CLI only)

TRIUX/SQUID MEG recordings are processed using Elekta MaxFilter to apply Signal Space Separation (SSS) and temporal SSS.

## 4. sync — Server Synchronization

Processed datasets can be synchronized to a central server with filtering and optional deletion of files not present in the source directory.

Config key: `RUN.sync`

## 5. Reporting

HTML reports summarize processing status, dataset contents, and potential issues.
