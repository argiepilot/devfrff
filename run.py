#!/usr/bin/env python3
"""Runner script for Germany VFR Approach Charts for ForeFlight BYOP."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from main import app

if __name__ == "__main__":
    # If no command is specified, default to process-realistic
    valid_commands = ["scrape", "download", "full-pipeline", "process-realistic", "info"]
    
    # Check if first argument is a valid command
    if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1] not in valid_commands):
        # No valid command specified, add process-realistic
        sys.argv.insert(1, "process-realistic")
    
    app() 