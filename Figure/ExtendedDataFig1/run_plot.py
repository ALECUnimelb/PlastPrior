"""Render ExtendedDataFig1 with original scientific logic and corrected UpSet alignment.

Prepare once: python Figure/_shared/reproduce.py prepare ExtendedDataFig1 --source-project PATH
Then run this file. Original export names retain historical figure numbering.
All inputs, baseline images, output figures, source tables and audits are ignored.
Use audit_alignment.py for the intentional layout revision; pixel identity to
the manuscript is no longer expected for the UpSet panel and composite.
"""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from reproduce import run
if __name__ == "__main__":
    run(HERE)
