#!/bin/bash
# Cross-platform SESHAT Pipeline installer using Python virtual environment or Conda

set -e

# Parse command line arguments
USE_CONDA=true  # Default to conda installation
while [[ $# -gt 0 ]]; do
    case $1 in
        --venv)
            USE_CONDA=false
            shift
            ;;
        --conda)
            USE_CONDA=true
            shift
            ;;
        --help|-h)
            echo "SESHAT Pipeline Installer"
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --venv      Use Python virtual environment instead of conda"
            echo "  --conda     Use conda environment (default)"
            echo "  --help, -h  Show this help message"
            echo ""
            echo "Default installation uses conda environment for better PyQt compatibility"
            echo "Virtual environment installation available with --venv flag"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [ "$USE_CONDA" = true ]; then
    echo "Installing SESHAT Pipeline with Conda environment (default)..."
else
    echo "Installing SESHAT Pipeline with Python virtual environment..."
fi

# Detect operating system
OS=$(uname -s)
ARCH=$(uname -m)

echo "Detected platform: $OS ($ARCH)"

# Function to find conda Python version
find_conda_python_version() {
    if command -v conda &> /dev/null; then
        # Check available Python versions in conda
        local available_versions=$(conda search python 2>/dev/null | grep "^python " | awk '{print $2}' | grep -E "^3\.(1[2-9]|[2-9][0-9])" | sort -V | tail -1)
        if [ -n "$available_versions" ]; then
            echo "$available_versions"
            return 0
        fi
    fi
    echo "3.12"  # Default fallback
    return 0
}

# Function to find Python installation
find_python() {
    # For conda installation, we don't need to search for system Python
    # conda will provide Python in the environment
    if [ "$USE_CONDA" = true ]; then
        # Just return a placeholder since conda will handle Python installation
        echo "conda-python"
        return 0
    fi
    
    # For venv installation, search for system Python 3.12+
    local python_with_tkinter=""
    local python_without_tkinter=""
    
    # For venv installation, prioritize system Python with tkinter
    for python_cmd in /usr/bin/python3 python3.13 python3.12 python3 python; do
        if command -v "$python_cmd" &> /dev/null; then
            local version=$($python_cmd --version 2>&1 | cut -d' ' -f2)
            local major=$(echo "$version" | cut -d'.' -f1)
            local minor=$(echo "$version" | cut -d'.' -f2)
            
            if [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; then
                # Test if tkinter is available (preferred for GUI)
                if $python_cmd -c "import tkinter" 2>/dev/null; then
                    if [ -z "$python_with_tkinter" ]; then
                        python_with_tkinter="$python_cmd"
                    fi
                else
                    if [ -z "$python_without_tkinter" ]; then
                        python_without_tkinter="$python_cmd"
                    fi
                fi
            fi
        fi
    done
    
    # Return best available Python for venv
    if [ -n "$python_with_tkinter" ]; then
        echo "$python_with_tkinter"
        return 0
    elif [ -n "$python_without_tkinter" ]; then
        echo "$python_without_tkinter"
        return 0
    fi
    
    return 1
}

# Find suitable Python installation
if [ "$USE_CONDA" = true ]; then
    # For conda, just verify conda is available - it will provide Python
    echo "🔍 Checking conda availability..."
    if ! command -v conda &> /dev/null; then
        echo "❌ Error: conda is not installed or not in PATH" >&2
        echo "   Please install Miniconda or Anaconda first:" >&2
        echo "   https://docs.conda.io/en/latest/miniconda.html" >&2
        exit 1
    fi
    echo "✅ Found conda: $(conda --version)"
    PYTHON="conda-python"  # Placeholder - conda will provide Python
else
    # For venv, find system Python interpreter
    echo "🔍 Finding Python interpreter..."
    if ! PYTHON=$(find_python); then
        echo "❌ Error: Python 3.12+ is required but not found" >&2
        echo "   Please install Python 3.12 or higher" >&2
        exit 1
    fi
    echo "✅ Found Python: $PYTHON ($($PYTHON --version))"
fi

# Check for GUI library availability and show appropriate info
if [ "$USE_CONDA" = true ]; then
    echo "ℹ️  GUI libraries will be installed via conda (PyQt6) for full functionality"
else
    if $PYTHON -c "import tkinter" 2>/dev/null; then
        echo "✅ GUI support: tkinter available"
    elif $PYTHON -c "import PyQt6.QtWidgets" 2>/dev/null; then
        echo "✅ GUI support: PyQt6 available"
    else
        echo "ℹ️  GUI libraries will be installed via PyQt6 for full functionality"
    fi
fi

# Check for uv and mention the benefits
if command -v uv &> /dev/null; then
    echo "✓ uv found - will use for faster package installation"
else
    echo "💡 uv will be installed in the virtual environment for faster package installation"
    echo "   (uv is 10-100x faster than pip for installing packages)"
fi

# Check if installation directory already exists and ask for confirmation
TARGET_DIR="$HOME/.local/bin/NatMEG-utils"

if [ -d "$TARGET_DIR" ]; then
    echo "NatMEG-utils installation already exists at $TARGET_DIR"
    echo "This will:"
    echo "  - Overwrite all Python scripts and configuration files"
    echo "  - Recreate the virtual environment (.venv)"
    echo "  - Reinstall all Python packages"
    echo ""
    read -p "Do you want to continue and overwrite the existing installation? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    echo "Proceeding with overwrite..."
fi

# Copy relevant files to local
RELEVANT_FILES=("install.sh" "natmeg_pipeline.py" "utils.py" "copy_to_cerberos.py" "maxfilter.py" "add_hpi.py" "bidsify.py" "sync_to_cir.py" "render_report.py" "README.md" "run_config.py" "requirements.txt" "sheshat_col.png") 
SOURCE_DIR=$(pwd)

# Create local bin directory
mkdir -p "$HOME/.local/bin"
mkdir -p "$TARGET_DIR"

echo "Copying project files..."
for file in "${RELEVANT_FILES[@]}"; do
    if [ -f "$SOURCE_DIR/$file" ]; then
        if [ -f "$TARGET_DIR/$file" ]; then
            # File exists, we already got permission above, so just copy
            cp "$SOURCE_DIR/$file" "$TARGET_DIR"
            echo "✓ Overwritten $file"
        else
            # New file, copy directly
            cp "$SOURCE_DIR/$file" "$TARGET_DIR"
            echo "✓ Copied $file"
        fi
    else
        echo "⚠ Warning: $file does not exist in $SOURCE_DIR"
    fi
done

if [ -d "$SOURCE_DIR/assets" ]; then
    rm -rf "$TARGET_DIR/assets"
    cp -R "$SOURCE_DIR/assets" "$TARGET_DIR/assets"
    echo "✓ Copied assets folder"
else
    echo "⚠ Warning: assets folder does not exist in $SOURCE_DIR"
fi

# Create environment (conda or venv)
if [ "$USE_CONDA" = true ]; then
    echo "Setting up Conda environment..."
    
    # Check if conda is available
    if ! command -v conda &> /dev/null; then
        echo "❌ Error: conda is not installed or not in PATH" >&2
        echo "   Please install Miniconda or Anaconda first:" >&2
        echo "   https://docs.conda.io/en/latest/miniconda.html" >&2
        exit 1
    fi
    
    CONDA_ENV_NAME="seshat_utils"
    
    # Remove existing conda environment if it exists
    if conda env list | grep -q -E "(seshat-utils|seshat_utils|natmeg-utils|natmeg_utils)"; then
        echo "Removing existing conda environment..."
        # Clean up both current and legacy environment names.
        conda env remove -n "seshat-utils" -y 2>/dev/null || true
        conda env remove -n "seshat_utils" -y 2>/dev/null || true
        conda env remove -n "natmeg-utils" -y 2>/dev/null || true
        conda env remove -n "natmeg_utils" -y 2>/dev/null || true
    fi
    
    # Create basic conda environment with Python and pip
    echo "Creating conda environment with Python and pip..."
    conda create -n "$CONDA_ENV_NAME" --channel conda-forge "python=3.12" pip uv -y 
    
    # Initialize conda for the current shell session
    source "$(conda info --base)/etc/profile.d/conda.sh"
    
    # Activate the environment
    conda activate "$CONDA_ENV_NAME"
    
    ENV_TYPE="conda"
    ENV_PATH="$CONDA_ENV_NAME"
    
else
    echo "Creating Python virtual environment..."
    VENV_PATH="$TARGET_DIR/.venv"
    
    if [ -d "$VENV_PATH" ]; then
        echo "Removing existing virtual environment..."
        rm -rf "$VENV_PATH"
    fi
    
    # Always create venv with standard Python first
    $PYTHON -m venv "$VENV_PATH"
    source "$VENV_PATH/bin/activate"
    ENV_TYPE="venv"
    ENV_PATH="$VENV_PATH"
fi

# Check if uv is available globally, if not install it in the environment
if command -v uv &> /dev/null; then
    echo "✓ Using system uv for package installation"
    USE_UV=true
else
    echo "Installing uv in $ENV_TYPE environment for faster package installation..."
    pip install --upgrade pip
    pip install uv
    if command -v uv &> /dev/null; then
        echo "✓ uv installed successfully in $ENV_TYPE environment"
        USE_UV=true
    else
        echo "⚠ uv installation failed, falling back to pip"
        USE_UV=false
    fi
fi

# Install requirements with uv or pip (same approach for both conda and venv)
echo "Installing Python dependencies..."
if [ "$USE_UV" = true ]; then
    if [ -f "$TARGET_DIR/requirements.txt" ]; then
        uv pip install -r "$TARGET_DIR/requirements.txt"
    else
        echo "Warning: requirements.txt not found, installing basic dependencies..."
        uv pip install numpy scipy pandas matplotlib scikit-learn mne mne-bids bids-validator h5py tqdm requests pyyaml jinja2 click psutil PyQt6
    fi
else
    if [ -f "$TARGET_DIR/requirements.txt" ]; then
        pip install -r "$TARGET_DIR/requirements.txt"
    else
        echo "Warning: requirements.txt not found, installing basic dependencies..."
        pip install numpy scipy pandas matplotlib scikit-learn mne mne-bids bids-validator h5py tqdm requests pyyaml jinja2 click psutil PyQt6
    fi
fi

echo "✓ Virtual environment created and dependencies installed"

# Determine shell config file
SHELL_CONFIG=""
if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ] || [ "$SHELL" = "/usr/bin/zsh" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "/bin/bash" ] || [ "$SHELL" = "/usr/bin/bash" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
else
    SHELL_CONFIG="$HOME/.profile"
fi

echo "Using shell config: $SHELL_CONFIG"

# Create the seshat executable
echo "Creating seshat executable..."

cat > "$HOME/.local/bin/NatMEG-utils/seshat" << EOF
#!/bin/bash
# SESHAT Pipeline Executable - Auto-generated with $ENV_TYPE environment

# SAFETY CHECKS - Prevent terminal crashes at all costs
set +e  # Don't exit on errors
set +u  # Don't exit on undefined variables
set +o pipefail  # Don't exit on pipe failures

# Multiple layers of error handling
trap 'echo "Warning: Error in seshat script, but terminal will remain open." >&2; exit 1' ERR
trap 'echo "Warning: Script interrupted, but terminal will remain open." >&2; exit 130' INT
trap 'echo "Warning: Script terminated, but terminal will remain open." >&2; exit 143' TERM

SCRIPT_PATH="\$HOME/.local/bin/NatMEG-utils/natmeg_pipeline.py"

# Environment-specific setup
ENV_TYPE="$ENV_TYPE"

if [ "\$ENV_TYPE" = "conda" ]; then
    # Conda environment setup
    CONDA_ENV_NAME="$CONDA_ENV_NAME"
    
    # Check if conda is available
    if ! command -v conda &> /dev/null; then
        echo "Error: conda command not found"
        echo "Please ensure conda is installed and in your PATH"
        exit 1
    fi
    
    # Check if conda environment exists
    if ! conda env list | grep -q "\$CONDA_ENV_NAME"; then
        echo "Error: Conda environment '\$CONDA_ENV_NAME' not found"
        echo "Please re-run the installation script with --conda flag"
        exit 1
    fi
    
    # Activate conda environment and run script
    source "\$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "\$CONDA_ENV_NAME"
    PYTHON_CMD="python"
    
else
    # Virtual environment setup
    VENV_PATH="\$HOME/.local/bin/NatMEG-utils/.venv"
    PYTHON_VENV="\$VENV_PATH/bin/python"
    
    # Check if virtual environment exists
    if [ ! -d "\$VENV_PATH" ]; then
        echo "Error: Virtual environment not found at \$VENV_PATH"
        echo "Please re-run the installation script."
        exit 1
    fi
    
    # Check if Python executable exists in venv
    if [ ! -f "\$PYTHON_VENV" ]; then
        echo "Error: Python executable not found in virtual environment"
        echo "Virtual environment may be corrupted. Please re-run the installation script."
        exit 1
    fi
    
    PYTHON_CMD="\$PYTHON_VENV"
fi

# Check if main script exists
if [ ! -f "\$SCRIPT_PATH" ]; then
    echo "Error: Could not find pipeline entrypoint at \$SCRIPT_PATH"
    echo "Please ensure the NatMEG-utils installation is complete"
    exit 1
fi

# Check if main script is readable
if [ ! -r "\$SCRIPT_PATH" ]; then
    echo "Error: Cannot read pipeline entrypoint at \$SCRIPT_PATH"
    echo "Please check file permissions"
    exit 1
fi

# Run the script with the appropriate Python
"\$PYTHON_CMD" "\$SCRIPT_PATH" "\$@"

# If the above fails and it's a GUI command, provide helpful error message
if [ \$? -ne 0 ] && [ "\$1" = "gui" ]; then
    echo ""
    echo "GUI failed to start. This may be due to PyQt issues."
    if [ "\$ENV_TYPE" = "venv" ]; then
        echo "Try installing with conda (default, better PyQt support):"
        echo "  bash install.sh"
    else
        echo "Try these solutions:"
        echo "  1. Reinstall with: bash install.sh"
        echo "  2. Check PyQt installation: conda list pyqt"
        echo "  3. Try venv installation: bash install.sh --venv"
    fi
    echo "  4. Use command-line interface instead: seshat run --config config.yml"
fi
EOF

# Make it executable
chmod +x "$HOME/.local/bin/NatMEG-utils/seshat"

# Create backward-compatible natmeg alias executable
cat > "$HOME/.local/bin/NatMEG-utils/natmeg" << 'EOF'
#!/bin/bash
# Backward-compatible alias for legacy command name.
exec "$HOME/.local/bin/NatMEG-utils/seshat" "$@"
EOF

# Make alias executable
chmod +x "$HOME/.local/bin/NatMEG-utils/natmeg"

# Add to PATH if not already there
if ! echo "$PATH" | grep -q "$HOME/.local/bin/NatMEG-utils"; then
    echo "Adding $HOME/.local/bin/NatMEG-utils to PATH in $SHELL_CONFIG"
    echo 'export PATH="$HOME/.local/bin/NatMEG-utils:$PATH"' >> "$SHELL_CONFIG"
    echo "Please run: source $SHELL_CONFIG"
else
    echo "$HOME/.local/bin/NatMEG-utils is already in PATH"
fi

# Create Linux desktop launcher for GUI usage.
if [ "$OS" = "Linux" ]; then
    DESKTOP_DIR="$HOME/.local/share/applications"
    DESKTOP_FILE="$DESKTOP_DIR/seshat.desktop"
    mkdir -p "$DESKTOP_DIR"

    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SESHAT
Comment=SESHAT Pipeline Config Editor
Exec=$HOME/.local/bin/NatMEG-utils/seshat gui
Icon=$HOME/.local/bin/NatMEG-utils/assets/seshat_col.png
Terminal=false
Categories=Science;Education;
StartupNotify=true
EOF

    chmod +x "$DESKTOP_FILE"
    echo "✓ Linux desktop app created at $DESKTOP_FILE"
fi

# Check environment
echo "Checking $ENV_TYPE environment..."

if [ "$ENV_TYPE" = "conda" ]; then
    # Check conda environment
    if conda env list | grep -q "$CONDA_ENV_NAME"; then
        echo "✓ Conda environment '$CONDA_ENV_NAME' found"
        
        # Initialize conda for the current shell session and activate
        source "$(conda info --base)/etc/profile.d/conda.sh"
        conda activate "$CONDA_ENV_NAME"
        if python -c "import mne, pandas, numpy; print('Core packages available')" 2>/dev/null; then
            echo "✓ Core packages (mne, pandas, numpy) successfully installed"
            
            # Test PyQt for GUI functionality
            if python -c "import PyQt6.QtWidgets" 2>/dev/null || python -c "import PyQt5.QtWidgets" 2>/dev/null; then
                echo "✓ PyQt available - GUI will work"
                ENV_EXISTS=true
            elif python -c "import tkinter" 2>/dev/null; then
                echo "✓ tkinter available - GUI will work (fallback)"
                ENV_EXISTS=true
            else
                echo "⚠ Warning: No GUI toolkit available - GUI features disabled"
                echo "  Command-line interface will still work"
                ENV_EXISTS=true
            fi
        else
            echo "⚠ Warning: Some required packages may be missing"
            ENV_EXISTS=false
        fi
    else
        echo "⚠ Warning: Conda environment not found"
        ENV_EXISTS=false
    fi
else
    # Check virtual environment
    VENV_PATH="$TARGET_DIR/.venv"
    
    if [ -d "$VENV_PATH" ] && [ -f "$VENV_PATH/bin/activate" ]; then
        echo "✓ Virtual environment found at $VENV_PATH"
        
        # Test if we can import key packages
        source "$VENV_PATH/bin/activate"
        if python -c "import mne, pandas, numpy; print('Core packages available')" 2>/dev/null; then
            echo "✓ Core packages (mne, pandas, numpy) successfully installed"
            
            # Test GUI toolkits
            if python -c "import PyQt6.QtWidgets" 2>/dev/null; then
                echo "✓ PyQt6 available - GUI will work"
                ENV_EXISTS=true
            elif python -c "import tkinter" 2>/dev/null; then
                echo "✓ tkinter available - GUI will work (fallback)"
                ENV_EXISTS=true
            else
                echo "⚠ Warning: No GUI toolkit available - GUI features disabled"
                echo "  Command-line interface will still work"
                ENV_EXISTS=true
            fi
        else
            echo "⚠ Warning: Some required packages may be missing"
            ENV_EXISTS=false
        fi
        deactivate
    else
        echo "⚠ Warning: Virtual environment not found or corrupted"
        ENV_EXISTS=false
    fi
fi

echo ""
echo "Installation complete!"
echo ""
echo "Testing the installation..."

# Test if the executable works
if (command -v seshat &> /dev/null || [ -f "$HOME/.local/bin/NatMEG-utils/seshat" ]) && [ -f "$HOME/.local/bin/NatMEG-utils/natmeg" ]; then
    echo "✓ seshat executable created successfully"
    echo "✓ natmeg alias created for backward compatibility"
    
    # Test basic execution only if environment exists
    if [ "$ENV_EXISTS" = true ] && [ -f "$HOME/.local/bin/NatMEG-utils/natmeg_pipeline.py" ]; then
        echo "✓ Virtual environment and main Python file ready"
        INSTALL_SUCCESS=true
    else
        echo "⚠ seshat executable created but virtual environment needs setup"
        INSTALL_SUCCESS=false   
    fi
else
    echo "✗ Failed to create seshat executable"
    INSTALL_SUCCESS=false
fi

echo ""
echo "Usage:"
echo "  seshat gui                      # Launch GUI"
echo "  seshat run --config config.yml   # Run pipeline"
echo "  seshat report --config config.yml # Generate HTML report only"
echo ""

# Conditional instructions based on installation status
if [ "$ENV_EXISTS" = false ]; then
    if [ "$USE_CONDA" = true ]; then
        echo "NEXT STEPS - Fix conda environment:"
        echo "  1. source $SHELL_CONFIG"
        echo "  2. conda env remove -n seshat_utils"
        echo "  3. cd $TARGET_DIR"
        echo "  4. bash install.sh --conda  # Recreate conda environment"
        echo "  5. Test with: seshat --help"
    else
        echo "NEXT STEPS - Fix virtual environment:"
        echo "  1. source $SHELL_CONFIG"
        echo "  2. cd $TARGET_DIR"
        echo "  3. rm -rf .venv  # Remove corrupted environment"
        echo "  4. $PYTHON -m venv .venv  # Recreate environment"
        echo "  5. source .venv/bin/activate"
        echo "  6. pip install -r requirements.txt"
        echo "  7. Test with: seshat --help"
        echo ""
        echo "  Alternative (if default conda fails):"
        echo "  bash install.sh --venv  # Use venv instead of conda"
    fi
elif [ "$INSTALL_SUCCESS" = true ]; then
    echo "✅ Installation complete and ready to use!"
    if [ "$USE_CONDA" = true ]; then
        echo "Using conda environment: $CONDA_ENV_NAME"
    fi
    echo "Test with: seshat --help"
else
    echo "TROUBLESHOOTING:"
    if [ "$USE_CONDA" = true ]; then
        echo "  - Check conda installation: conda --version"
        echo "  - Check environment: conda env list"
        echo "  - Recreate environment: bash install.sh --conda"
    else
        echo "  - Ensure Python 3.12+ is working: $PYTHON --version"
        echo "  - Try venv installation: bash install.sh --venv"
    fi
    echo "  - Check PATH: echo \$PATH"
    echo "  - View executable: cat ~/.local/bin/NatMEG-utils/seshat"
    echo "  - Re-run installer if needed"
fi