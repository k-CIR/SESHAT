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
seshat gui
seshat run --config config.yml
seshat --help
```

> **Note:** The `natmeg` command is still available as a deprecated alias for backwards compatibility.

## Minimal Usage Example

```bash
# Create configuration
seshat create-config --output config.yml

# Run the full pipeline
seshat run --config config.yml
```

## Documentation

- Overview: docs/index.md
- Installation: docs/installation.md
- User Guide: docs/user-guide/
- Developer Documentation: docs/developer/
- Reference: docs/reference/
