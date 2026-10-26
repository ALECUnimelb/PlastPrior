"""Generate Fig. 5 from the locked PlastPrior analysis."""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from current import run
if __name__ == "__main__":
    run(HERE)
