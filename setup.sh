#!/bin/bash

# Define colors for cleaner output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting eBook Translator Setup...${NC}"

# ---------------------------------------------------------
# 1. Check for Homebrew (Needed for Calibre & fallback Python)
# ---------------------------------------------------------
if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}Homebrew not found. Installing Homebrew...${NC}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for Apple Silicon or Intel
    if [[ $(uname -m) == 'arm64' ]]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> /Users/$USER/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        echo 'eval "$(/usr/local/bin/brew shellenv)"' >> /Users/$USER/.zprofile
        eval "$(/usr/local/bin/brew shellenv)"
    fi
else
    echo -e "${GREEN}Homebrew is already installed.${NC}"
fi

# ---------------------------------------------------------
# 2. Check for Python 3
# ---------------------------------------------------------
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version)
    echo -e "${GREEN}Found existing Python: $PY_VERSION${NC}"
else
    echo -e "${YELLOW}Python 3 not found. Installing default Python via Homebrew...${NC}"
    brew install python
fi

# Check for Tkinter (Required for the GUI)
# Some system pythons don't have it bundled.
if ! python3 -c "import tkinter" &> /dev/null; then
    echo -e "${YELLOW}Tkinter module missing. Attempting to install python-tk...${NC}"
    brew install python-tk
fi

# ---------------------------------------------------------
# 3. Install Calibre (Needed for ebook-convert)
# ---------------------------------------------------------
echo -e "${YELLOW}Checking for Calibre (needed for .mobi/.azw3 inputs)...${NC}"
if ! -d "/Applications/calibre.app"; then
    echo "Installing Calibre via Homebrew Cask..."
    brew install --cask calibre
else
    echo -e "${GREEN}Calibre app found.${NC}"
fi

# ---------------------------------------------------------
# 4. Link ebook-convert to PATH
# ---------------------------------------------------------
echo -e "${YELLOW}Configuring ebook-convert CLI tool...${NC}"
CALIBRE_BIN="/Applications/calibre.app/Contents/MacOS/ebook-convert"

if [ -f "$CALIBRE_BIN" ]; then
    # Check if it's already in the path
    if ! command -v ebook-convert &> /dev/null; then
        echo "Linking ebook-convert to /usr/local/bin..."
        # We use sudo here because /usr/local/bin is often protected
        if [ ! -d "/usr/local/bin" ]; then sudo mkdir -p /usr/local/bin; fi
        sudo ln -s "$CALIBRE_BIN" /usr/local/bin/ebook-convert
    else
        echo -e "${GREEN}ebook-convert is already correctly linked.${NC}"
    fi
else
    echo -e "${RED}Warning: Could not find Calibre binary. Conversion of .mobi files will fail.${NC}"
fi

# ---------------------------------------------------------
# 5. Set up Virtual Environment & Dependencies
# ---------------------------------------------------------
echo -e "${YELLOW}Setting up Python Virtual Environment...${NC}"

# Remove old venv if it was broken or different python version
# rm -rf venv 

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Created new 'venv'."
else
    echo "Using existing 'venv'."
fi

# Activate environment
source venv/bin/activate

echo -e "${YELLOW}Installing/Updating Python libraries...${NC}"
pip install --upgrade pip
# Installing the specific libraries your backend needs
pip install beautifulsoup4 lxml deepl google-generativeai deep-translator

# ---------------------------------------------------------
# 6. Run the App
# ---------------------------------------------------------
echo -e "${GREEN}---------------------------------------${NC}"
echo -e "${GREEN}Setup Complete! Launching App...${NC}"
echo -e "${GREEN}---------------------------------------${NC}"

python gui_app.py