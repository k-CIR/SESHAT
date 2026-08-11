# Pipeline Architecture

SESHAT implements a modular preprocessing pipeline for MEG/EEG datasets. The architecture separates acquisition synchronization, preprocessing, data standardization, and reporting.

## Core Components

1. Data ingestion and synchronization from acquisition systems.
2. Preprocessing steps including HPI coregistration and MaxFilter.
3. Dataset standardization through BIDS conversion.
4. Reporting and synchronization of processed data to central servers.

## Processing Flow

Raw data are copied from acquisition computers to a central processing environment. The pipeline then performs preprocessing steps specific to the recording modality.

For TRIUX/SQUID systems, MaxFilter is used for Signal Space Separation and noise suppression. For OPM systems, HPI information is integrated using digitization data.

Processed data can then be synchronized to central storage or servers for long‑term archiving and analysis.

## Metadata and Provenance

Pipeline execution generates metadata describing files, processing steps, and parameters. Tracking this metadata allows reproducibility and auditing of preprocessing operations.

Databases and versioning tools can maintain file inventories, run logs, and lineage relationships between raw and derived datasets.
