"""Restore the approved Nature Fig. 1 PNG exactly; this is not a code redraw.

The original editable schematic is not available in the retained figure bundle.
The 921 x 515 asset is preserved without upscaling, recolouring or relabelling.
Prepare its ignored input with Figure/_shared/reproduce.py before running.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from reproduce import run

if __name__ == "__main__":
    run(HERE)
