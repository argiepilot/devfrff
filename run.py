#!/usr/bin/env python3
"""Runner script for VFR Charts for ForeFlight BYOP."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from main import app

if __name__ == "__main__":
    # If no command is specified, default to process-all (unified processing)
    valid_commands = [
        "scrape",
        "download",
        "full-pipeline",
        "process-realistic",
        "process-all",
        "process-faa-sectional",
        "process-faa-terminal",
        "info",
    ]
    
    # Check if first argument is a valid command
    # Skip insertion if:
    # 1. No arguments provided (len(sys.argv) == 1)
    # 2. First argument is not a valid command AND it's not a flag (doesn't start with '-')
    # This prevents breaking flags like --help, --version, etc.
    if len(sys.argv) == 1 or (
        len(sys.argv) > 1
        and sys.argv[1] not in valid_commands
        and not sys.argv[1].startswith("-")
    ):
        # No valid command specified: default to process-all, but prompt interactively
        # (y/n questions defaulting to Yes)
        sys.argv.insert(1, "process-all")
        sys.argv.insert(2, "--interactive")
    
    app()