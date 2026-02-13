#!/bin/bash
set -e

# Paths
SOURCE_DIR="/git/apollos-ai"
TARGET_DIR="/a0"

# Copy repository files if run_ui.py is missing in /a0 (if the volume is mounted)
if [ ! -f "$TARGET_DIR/run_ui.py" ]; then
    echo "   ├─ volume sync   copying application files..."
    cp -rn --no-preserve=ownership,mode "$SOURCE_DIR/." "$TARGET_DIR"
fi
