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

```bash
# Clone the repository
git clone https://github.com/NatMEG/NatMEG-utils.git
cd NatMEG-utils

# Run the installer
bash install.sh
```

The installer will:
- Detect your operating system (macOS/Linux) and conda installation
- Create a `natmeg` executable in `~/.local/bin/`
- Add `~/.local/bin` to your PATH if needed
- Guide you through conda environment setup
- Provide clear troubleshooting instructions

After installation, you can use the pipeline from anywhere:
```bash
natmeg gui                     # Launch GUI
natmeg run --config config.yml # Run pipeline
natmeg --help                  # Show all options
```

### Manual Installation

If you prefer manual setup:

#### 1. Create Conda Environment
```bash
conda create -n natmeg_utils python=3.9 -y
conda activate natmeg_utils
```

#### 2. Install Dependencies
```bash
# Core dependencies
conda install mne mne-bids numpy pandas matplotlib pyyaml

# Optional dependencies for advanced features
pip install json5  # For JSON files with comments

# Install pipeline in development mode
pip install -e .
```

#### 3. Add to PATH (Optional)
```bash
# Add repository to PATH for global access
echo 'export PATH="$HOME/Sites/NatMEG-utils:$PATH"' >> ~/.zshrc  # or ~/.bashrc
source ~/.zshrc
```

### Prerequisites

- **Python 3.9+**: Required for all pipeline components
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
# Check conda environments
conda env list

# Recreate environment if needed
conda remove -n natmeg_utils --all -y
conda create -n natmeg_utils python=3.9 -y
conda activate natmeg_utils
cd ~/Sites/NatMEG-utils
pip install -e .
```

### Runtime Issues

**Module import errors:**
```bash
# Ensure you're in the correct environment
conda activate natmeg_utils

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
