# "SESHAT - Scripts for Extraction, Synchronisation, HPI + Analog alignment and Transfer"

SESHAT is a MEG/EEG preprocessing pipeline designed for NatMEG datasets. It provides tools for copying acquisition data, preprocessing recordings, synchronizing results to servers, and generating processing reports.

## Quick Installation

```bash
git clone git@github.com:k-CIR/SESHAT.git
cd SESHAT
bash install.sh
```

After installation:

```bash
natmeg gui
natmeg run --config config.yml
natmeg --help
```

## Minimal Usage Example

```bash
# Create configuration
natmeg create-config --output config.yml

# Run the full pipeline
natmeg run --config config.yml
```

## Documentation

- Overview: docs/index.md
- Installation: docs/installation.md
- User Guide: docs/user-guide/
- Developer Documentation: docs/developer/
- Reference: docs/reference/
