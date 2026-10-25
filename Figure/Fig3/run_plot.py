"""Reproduce Nature Fig3 using the original scientific/R plotting module.

Prepare once: python Figure/_shared/reproduce.py prepare Fig3 --source-project PATH
Then run this file. Original export names retain historical figure numbering.
All inputs, baseline images, output figures, source tables and audits are ignored.
"""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from reproduce import run
if __name__ == "__main__":
    run(HERE)
