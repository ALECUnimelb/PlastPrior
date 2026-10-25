"""Reproduce Nature Fig. 2 with unchanged PBMT scientific and R plotting code.

Run Figure/_shared/reproduce.py prepare Fig2 --source-project PATH once.
The historical module/export names refer to its former Figure 4 position.
"""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from reproduce import run
if __name__ == "__main__":
    run(HERE)
