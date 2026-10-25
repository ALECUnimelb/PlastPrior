"""Regenerate Extended Data Fig. 3 using Fig4's original sensitivity module.

Prepare: python Figure/_shared/reproduce.py prepare ExtendedDataFig3 --source-project PATH
Then run this script. The source implementation lives in Figure/Fig4; it is
rerun from the frozen input, not read from Fig4/output. The original module
exports its complete audited table/panel bundle; this entry selects its
positive_input_context composite as ExtendedDataFig3.png.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from reproduce import run

if __name__ == "__main__":
    run(HERE)
