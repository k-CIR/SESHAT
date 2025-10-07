---
title: NatMEG Processing Pipeline Utility Scripts
---

# NatMEG Processing Pipeline

Comprehensive MEG/EEG preprocessing pipeline for NatMEG data including BIDS conversion, MaxFilter processing, HPI coregistration, and data synchronization utilities.

Note: The last step, to push project to the CIR-server, is not yet included. Also everything is in devlopment mode so feedback and improvements are welcome.

Read full documentation on how to use the pipeline [here](https://k-cir.github.io/cir-wiki/natmeg/preprocessing)

## Overview

This pipeline provides end-to-end processing for:
- **TRIUX/SQUID MEG** data from Elekta systems
- **OPM MEG** data from Kaptah/OPM systems  
- **EEG** data collected through TRIUX

## Installation

### Automated Installation (Recommended)

The NatMEG pipeline includes an automated installation script that sets up everything you need:

#### Default Installation (Conda Environment)
```bash
# Clone the repository
git clone https://github.com/NatMEG/NatMEG-utils.git
cd NatMEG-utils

# Run the installer (uses conda by default)
bash install.sh

# View all installer options
bash install.sh --help
```

#### Alternative Installation (Python Virtual Environment)
```bash
# Clone the repository
git clone https://github.com/NatMEG/NatMEG-utils.git
cd NatMEG-utils

# Run the installer with venv flag
bash install.sh --venv
```**Benefits of conda installation (now default):**
- **Better PyQt Compatibility**: Provides isolated Python environment that avoids system conflicts
- **Linux Compatibility**: Works well on enterprise Linux distributions (Rocky/RHEL/CentOS)
- **Dependency Isolation**: Prevents conflicts with system-installed Python packages
- **Reliability**: More consistent installation experience across different systems

The installer will:
- Detect your operating system (macOS/Linux) and conda installation  
- Create a `natmeg` executable in `~/.local/bin/`
- Add `~/.local/bin` to your PATH if needed
- Set up either Python venv or conda environment based on your choice
- Provide clear troubleshooting instructions

After installation, you can use the pipeline from anywhere:
```bash
natmeg gui                     # Launch GUI
natmeg run --config config.yml # Run pipeline
natmeg --help                  # Show all options
```

### Manual Installation

If you prefer manual setup:

#### Option 1: Conda Environment (Recommended for Linux Rocky)
```bash
# Create basic conda environment
conda create -n natmeg-utils python=3.12 pip -y
conda activate natmeg-utils

# Install dependencies via pip (same as venv approach)
pip install -r requirements.txt
```

#### Option 2: Python Virtual Environment
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

#### 3. Add to PATH (Optional)
```bash
# Add repository to PATH for global access
echo 'export PATH="$HOME/Sites/NatMEG-utils:$PATH"' >> ~/.zshrc  # or ~/.bashrc
source ~/.zshrc
```

### Prerequisites

- **Python 3.12+**: Required for all pipeline components
- **Conda/Miniconda**: Recommended for environment management
- **Git**: For cloning the repository
- **Operating System**: macOS or Linux (Windows support coming soon)

## Quick Start

> **Note**: Install the pipeline first using `bash install.sh` (see [Installation](#installation) section above)

### Using the natmeg Command

After installation, you can use the `natmeg` command from anywhere:

```bash
# Launch GUI configuration interface
natmeg gui

# Run complete pipeline
natmeg run --config config.yml

# Run specific components
natmeg copy --config config.yml      # Data synchronization only
natmeg hpi --config config.yml       # HPI coregistration only  
natmeg maxfilter --config config.yml # MaxFilter processing only
natmeg bidsify --config config.yml   # BIDS conversion only

# Sync data to remote server (new interface)
natmeg sync --create-config                         # Generate example server config
natmeg sync --server-config servers.yml --test      # Test default server connection
natmeg sync --directory /data/project               # Sync directory (default server 'cir')
natmeg sync --config project_config.yml --dry-run   # Derive dir from project config

# Show help
natmeg --help
```

## Pipeline Components

### 1. Data Synchronization (`copy_to_cerberos.py`)

Synchronizes raw data between storage systems (Sinuhe/Kaptah → Cerberos).

### 2. HPI Coregistration (`add_hpi.py`)

Performs head localization for OPM-MEG using HPI coils and Polhemus digitization.


### 3. MaxFilter Processing (`maxfilter.py`)

Applies Elekta MaxFilter with Signal Space Separation (SSS) and temporal extension (tSSS).


### 4. BIDS Conversion (`bidsify.py`)

Converts NatMEG data to BIDS format and organizes it into a BIDS-compliant folder structure.

## Troubleshooting

### Installation Issues

**PyQt Issues on Linux Rocky/RHEL:**
```bash
# Default conda installation should work out of the box
bash install.sh

# If you previously used venv and had issues, conda is now default
# Creates isolated Python environment avoiding system conflicts
```

**Conda not found:**
```bash
# Install conda first
# macOS:
brew install miniconda
# or download from: https://docs.conda.io/en/latest/miniconda.html

# Linux:
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
```

**natmeg command not found:**
```bash
# Check if ~/.local/bin is in PATH
echo $PATH

# If not, add it to your shell config
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc  # or ~/.bashrc
source ~/.zshrc
```

**Environment activation fails:**
```bash
# For conda environments (default)
conda env list
conda env remove -n natmeg_utils -y  # Remove corrupted environment
bash install.sh  # Recreate with conda (default)

# For virtual environments  
rm -rf .venv  # Remove corrupted environment
bash install.sh --venv  # Recreate with venv
```

### Platform-Specific Issues

**Linux Rocky/RHEL/CentOS - PyQt GUI Issues:**

The GUI may fail to start on enterprise Linux distributions due to PyQt compatibility issues with system libraries. **Solution: Use conda installation**

```bash
# Recommended approach
bash install.sh --conda

# If already installed with pip/venv, switch to conda:
cd ~/Sites/NatMEG-utils
bash install.sh --conda  # This will replace the existing installation
```

**Why conda is now the default:**
- Provides isolated Python environment separate from system Python
- No conflicts with system-installed Python packages
- Better compatibility across different operating systems and distributions
- Same requirements.txt installation but in isolated conda environment
- Resolves PyQt issues commonly seen with system Python installations

### Runtime Issues

**Module import errors:**
```bash
# For conda environments
conda activate natmeg-utils
conda list  # Check installed packages

# For virtual environments
source .venv/bin/activate
pip list  # Check installed packages

# Install missing dependencies
pip install mne mne-bids pyyaml
```

**Permission errors:**
```bash
# Make natmeg executable
chmod +x ~/.local/bin/natmeg

# Check file permissions
ls -la ~/.local/bin/natmeg
```

**Terminal crashes:**
The natmeg script includes safety checks to prevent terminal crashes. If issues persist:
```bash
# View the generated script
cat ~/.local/bin/natmeg

# Regenerate with latest safety checks
cd ~/Sites/NatMEG-utils
bash install.sh
```

---

## Contributions

Improvements are welcomed! The pipeline includes robust installation and execution scripts that work across different environments.

**Development Guidelines:**
- Do not change scripts locally for personal use
- Follow GitHub conventions: create branches or fork the repository
- Make pull requests for any modifications
- Test installation script on both macOS and Linux before submitting changes
- Ensure compatibility with different conda installations and shell environments

**Testing the Installation:**
```bash
# Test on clean environment
bash install.sh

# Verify functionality
natmeg --help
natmeg gui
```
