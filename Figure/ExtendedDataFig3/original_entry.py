"""Dispatch to the single canonical sensitivity implementation in Fig4.

This avoids divergent scientific copies between the main and supplementary
figures. All command-line arguments, including explicit input/output paths,
are forwarded to the original portable entry without changing its calculations.
"""
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    entry = Path(__file__).resolve().parents[1] / "Fig4" / "original_entry.py"
    subprocess.run([sys.executable, str(entry), *sys.argv[1:]], check=True)
