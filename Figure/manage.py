"""Manage fixed figure destinations. Approve only after the user accepts a review."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'_shared'))
from managed import MANAGED,approve,refresh_index

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('index')
    sub.add_parser('approve').add_argument('figure',choices=sorted(MANAGED))
    args=parser.parse_args()
    if args.action=='approve': approve(args.figure)
    else: refresh_index()
