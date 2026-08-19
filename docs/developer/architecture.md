# Pipeline Architecture

SESHAT implements a modular preprocessing pipeline for MEG/EEG datasets. The architecture separates acquisition synchronization, preprocessing, data standardization, and reporting.

## Package Structure

```
seshat/
├── __init__.py          # version + description
├── cli.py               # CLI entry point (seshat / natmeg commands)
├── config.py            # config I/O, migration, Tkinter GUI
├── utils.py             # logging, path helpers, shared utilities
└── stages/
    ├── __init__.py
    ├── copy.py          # copy_raw stage (was copy_to_cerberos.py)
    ├── opm_preprocess.py
    ├── maxfilter.py
    ├── sync.py          # sync stage (was sync_to_cir.py)
    └── report.py        # HTML report generation (was render_report.py)
```

## Core Components

1. Data ingestion and synchronization from acquisition systems (`stages/copy.py`).
2. Preprocessing steps including HPI coregistration and OPM analog alignment (`stages/opm_preprocess.py`).
3. MaxFilter for TRIUX/SQUID recordings (`stages/maxfilter.py`).
4. Dataset standardization through BIDS conversion (stub; not yet implemented).
5. Reporting and synchronization of processed data to central servers (`stages/report.py`, `stages/sync.py`).

## Processing Flow

Raw data are copied from acquisition computers to a central processing environment. The pipeline then performs preprocessing steps specific to the recording modality.

For TRIUX/SQUID systems, MaxFilter is used for Signal Space Separation and noise suppression. For OPM systems, HPI information is integrated using digitization data.

Processed data can then be synchronized to central storage or servers for long‑term archiving and analysis.

## Metadata and Provenance

Pipeline execution generates metadata describing files, processing steps, and parameters. Tracking this metadata allows reproducibility and auditing of preprocessing operations.

Databases and versioning tools can maintain file inventories, run logs, and lineage relationships between raw and derived datasets.
