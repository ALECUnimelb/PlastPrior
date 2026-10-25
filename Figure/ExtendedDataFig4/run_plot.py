"""Restore the exact historical dashboard screenshot in Extended Data Fig. 4.

Prepare: python Figure/_shared/reproduce.py prepare ExtendedDataFig4 --source-project PATH
Then run this file. It restores the authenticated embedded PNG without edits.
It does not rebuild or screenshot a live dashboard: the original capture
environment is not part of the retained plotting bundle.

Known historical limitation retained for fidelity: the pictured literature
panel says 1104 and 'PubMed audit: 655 query hits - not scored', while the frozen
analysis selects PubMed 655 as its formal literature count. Both yield the same
score tier, but their provenance descriptions differ. This screenshot must not
be presented as evidence of current dashboard behavior or corrected data labels.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from reproduce import run

if __name__ == "__main__":
    run(HERE)
