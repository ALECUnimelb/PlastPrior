"""Prepare the current figure data together, without rendering or rescoring."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'_shared'))
from preparation import CURRENT, FROZEN, prepare

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figures',nargs='+',choices=CURRENT+FROZEN,default=CURRENT,
                        help='Default: all current-dataset figures and the SI table. Legacy figures require explicit selection.')
    parser.add_argument('--check',action='store_true',help='Check against current tables in temporary storage; do not publish data.')
    args=parser.parse_args()
    prepare(args.figures,check_existing=args.check,install=not args.check)
