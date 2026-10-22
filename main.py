"""Inspect local source inputs without running chemical prioritisation."""

import argparse
from pathlib import Path

from plastprior.inputs import inspect_inputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"),
                        help="Input directory; relative paths resolve from the project root.")
    args = parser.parse_args()
    print("Inspecting source files and supporting input presence...", flush=True)
    report = inspect_inputs(args.data_root)
    for title, frame in (("Source files", report.sources[["source", "version", "status", "detail"]]),
                         ("Source-native tables", report.tables),
                         ("Supporting inputs (presence only)", report.supporting)):
        print(f"\n{title}\n{frame.to_string(index=False)}")
    print("\nInspection passed." if report.passed else "\nInspection failed; review the reported issues.")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
