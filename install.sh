#!/bin/bash
# Cross-platform NatMEG Pipeline installer using Python virtual environment or Conda

set -e

# Parse command line arguments
USE_CONDA=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --conda)
            USE_CONDA=true
            shift
            ;;
        --help|-h)
            echo "NatMEG Pipeline Installer"
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --conda     Use conda environment instead of Python venv (recommended for Linux Rocky)"
            echo "  --help, -h  Show this help message"
            echo ""
            echo "Default installation uses Python virtual environment (.venv)"
            echo "Conda installation may resolve PyQt issues on some Linux distributions"
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
    echo "Installing NatMEG Pipeline with Conda environment..."
else
    echo "Installing NatMEG Pipeline with Python virtual environment..."
fi

# Detect operating system
OS=$(uname -s)
ARCH=$(uname -m)

echo "Detected platform: $OS ($ARCH)"

# Function to find Python installation
find_python() {
    # Check for Python 3.8+ (required for modern packages)
    local python_with_tkinter=""
    local python_without_tkinter=""
    
    # Prioritize system Python which usually has tkinter, then check other versions
    for python_cmd in /usr/bin/python3 python3.12 python3.11 python3.10 python3.9 python3.8 python3 python; do
        if command -v "$python_cmd" &> /dev/null; then
            local version=$($python_cmd --version 2>&1 | cut -d' ' -f2)
            local major=$(echo "$version" | cut -d'.' -f1)
            local minor=$(echo "$version" | cut -d'.' -f2)
            
            if [ "$major" -eq 3 ] && [ "$minor" -ge 8 ]; then
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
    
    # Prefer Python with tkinter, but accept one without if that's all we have
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
# Find Python interpreter
echo "🔍 Finding Python interpreter..."
if ! PYTHON=$(find_python); then
    echo "❌ Error: Python 3.8+ is required but not found" >&2
    echo "   Please install Python 3.8 or higher" >&2
    exit 1
fi

echo "✅ Found Python: $PYTHON ($($PYTHON --version))"

# Check for GUI library availability and show appropriate info
if $PYTHON -c "import tkinter" 2>/dev/null; then
    echo "✅ GUI support: tkinter available"
elif $PYTHON -c "import PyQt6.QtWidgets" 2>/dev/null; then
    echo "✅ GUI support: PyQt6 available"
else
    echo "ℹ️  GUI libraries will be installed via PyQt6 for full functionality"
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
RELEVANT_FILES=("install.sh" "natmeg_pipeline.py" "utils.py" "copy_to_cerberos.py" "maxfilter.py" "add_hpi.py" "bidsify.py" "sync_to_cir.py" "render_report.py" "README.md" "run_config.py" "requirements.txt") 
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
    
    CONDA_ENV_NAME="natmeg_utils"
    
    # Remove existing conda environment if it exists
    if conda env list | grep -q -E "($CONDA_ENV_NAME|natmeg_utils)"; then
        echo "Removing existing conda environment..."
        # Try both possible names
        conda env remove -n "$CONDA_ENV_NAME" -y 2>/dev/null || true
    fi
    
    # Create basic conda environment with Python and pip
    echo "Creating conda environment with Python and pip..."
    conda create -n "$CONDA_ENV_NAME" python=>3.12 pip uv -y
    
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

# Create the natmeg executable
echo "Creating natmeg executable..."

cat > "$HOME/.local/bin/NatMEG-utils/natmeg" << EOF
#!/bin/bash
# NatMEG Pipeline Executable - Auto-generated with $ENV_TYPE environment

# SAFETY CHECKS - Prevent terminal crashes at all costs
set +e  # Don't exit on errors
set +u  # Don't exit on undefined variables
set +o pipefail  # Don't exit on pipe failures

# Multiple layers of error handling
trap 'echo "Warning: Error in natmeg script, but terminal will remain open." >&2; exit 1' ERR
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
    echo "Error: Could not find natmeg_pipeline.py at \$SCRIPT_PATH"
    echo "Please ensure the NatMEG-utils installation is complete"
    exit 1
fi

# Check if main script is readable
if [ ! -r "\$SCRIPT_PATH" ]; then
    echo "Error: Cannot read natmeg_pipeline.py at \$SCRIPT_PATH"
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
        echo "Try installing with conda (better PyQt support on some systems):"
        echo "  bash install.sh --conda"
    else
        echo "Try these solutions:"
        echo "  1. Reinstall with: bash install.sh --conda"
        echo "  2. Check PyQt installation: conda list pyqt"
    fi
    echo "  3. Use command-line interface instead: natmeg run --config config.yml"
fi
EOF

# Make it executable
chmod +x "$HOME/.local/bin/NatMEG-utils/natmeg"

# Add to PATH if not already there
if ! echo "$PATH" | grep -q "$HOME/.local/bin/NatMEG-utils"; then
    echo "Adding $HOME/.local/bin/NatMEG-utils to PATH in $SHELL_CONFIG"
    echo 'export PATH="$HOME/.local/bin/NatMEG-utils:$PATH"' >> "$SHELL_CONFIG"
    echo "Please run: source $SHELL_CONFIG"
else
    echo "$HOME/.local/bin/NatMEG-utils is already in PATH"
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
if command -v natmeg &> /dev/null || [ -f "$HOME/.local/bin/NatMEG-utils/natmeg" ]; then
    echo "✓ natmeg executable created successfully"
    
    # Test basic execution only if environment exists
    if [ "$ENV_EXISTS" = true ] && [ -f "$HOME/.local/bin/NatMEG-utils/natmeg_pipeline.py" ]; then
        echo "✓ Virtual environment and main Python file ready"
        INSTALL_SUCCESS=true
    else
        echo "⚠ natmeg executable created but virtual environment needs setup"
        INSTALL_SUCCESS=false   
    fi
else
    echo "✗ Failed to create natmeg executable"
    INSTALL_SUCCESS=false
fi

echo ""
echo "Usage:"
echo "  natmeg gui                      # Launch GUI"
echo "  natmeg run --config config.yml   # Run pipeline"
echo "  natmeg report --config config.yml # Generate HTML report only"
echo ""

# Conditional instructions based on installation status
if [ "$ENV_EXISTS" = false ]; then
    if [ "$USE_CONDA" = true ]; then
        echo "NEXT STEPS - Fix conda environment:"
        echo "  1. source $SHELL_CONFIG"
        echo "  2. conda env remove -n natmeg-utils"
        echo "  3. cd $TARGET_DIR"
        echo "  4. bash install.sh --conda  # Recreate conda environment"
        echo "  5. Test with: natmeg --help"
    else
        echo "NEXT STEPS - Fix virtual environment:"
        echo "  1. source $SHELL_CONFIG"
        echo "  2. cd $TARGET_DIR"
        echo "  3. rm -rf .venv  # Remove corrupted environment"
        echo "  4. $PYTHON -m venv .venv  # Recreate environment"
        echo "  5. source .venv/bin/activate"
        echo "  6. pip install -r requirements.txt"
        echo "  7. Test with: natmeg --help"
        echo ""
        echo "  Alternative (recommended for Linux Rocky):"
        echo "  bash install.sh --conda  # Use conda instead of venv"
    fi
elif [ "$INSTALL_SUCCESS" = true ]; then
    echo "✅ Installation complete and ready to use!"
    if [ "$USE_CONDA" = true ]; then
        echo "Using conda environment: $CONDA_ENV_NAME"
    fi
    echo "Test with: natmeg --help"
else
    echo "TROUBLESHOOTING:"
    if [ "$USE_CONDA" = true ]; then
        echo "  - Check conda installation: conda --version"
        echo "  - Check environment: conda env list"
        echo "  - Recreate environment: bash install.sh --conda"
    else
        echo "  - Ensure Python 3.8+ is working: $PYTHON --version"
        echo "  - Try conda installation: bash install.sh --conda"
    fi
    echo "  - Check PATH: echo \$PATH"
    echo "  - View executable: cat ~/.local/bin/NatMEG-utils/natmeg"
    echo "  - Re-run installer if needed"
fi