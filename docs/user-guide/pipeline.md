# Pipeline Stages

The NatMEG pipeline processes MEG/EEG data through several stages.

## 1. Data Copy

Raw data are copied from acquisition computers (SQUID/OPM systems) to a central processing machine. This step ensures consistent project structure and data availability.

## 2. HPI Coregistration

For OPM-MEG recordings, head position indicator (HPI) information is added using Polhemus digitization data.

## (3) MaxFilter Processing (Legacy, CLI only)

TRIUX/SQUID MEG recordings are processed using Elekta MaxFilter to apply Signal Space Separation (SSS) and temporal SSS.

## 4. Server Synchronization

Processed datasets can be synchronized to a central server with filtering and optional deletion of files not present in the source directory.

## 5. Reporting

HTML reports summarize processing status, dataset contents, and potential issues.
