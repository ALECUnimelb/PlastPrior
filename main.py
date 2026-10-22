"""Inspect local source inputs without running chemical prioritisation."""

import argparse
from pathlib import Path

from plastprior.inputs import build_source_records, inspect_inputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"),
                        help="Input directory; relative paths resolve from the project root.")
    parser.add_argument("--require-supporting-inputs", action="store_true",
                        help="Also require all declared auxiliary files and directories to be present; "
                             "this does not validate their contents.")
    parser.add_argument("--output-dir", type=Path, default=Path("results"),
                        help="Inspection report directory; relative paths resolve from the project root.")
    parser.add_argument("--assemble-records", action="store_true",
                        help="Also assemble source inventory records; no identity resolution or deduplication.")
    parser.add_argument("--resolve-identities", action="store_true",
                        help="Assemble records, resolve structures and aggregate by full InChIKey.")
    args = parser.parse_args(argv)
    print("Inspecting source files and supporting input presence...", flush=True)
    report = inspect_inputs(args.data_root)
    for title, frame in (("Source files", report.sources[["source", "version", "status", "detail"]]),
                         ("Source-native tables", report.tables),
                         ("Supporting inputs (presence only)", report.supporting)):
        print(f"\n{title}\n{frame.to_string(index=False)}")
    output_dir = args.output_dir.expanduser()
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir
    report.write_reports(output_dir)
    print("\nStage 1 source inspection: " + ("Passed" if report.sources_passed else "Failed"))
    supporting_status = (
        "Not applicable (no groups declared)" if report.supporting.empty
        else "Present (contents not validated)" if report.supporting_present
        else "Incomplete; review the supporting-input report"
    )
    print("Supporting inputs: " + supporting_status)
    print(f"Inspection reports: {output_dir}")
    passed = report.passed if args.require_supporting_inputs else report.sources_passed
    if passed and (args.assemble_records or args.resolve_identities):
        records = build_source_records(args.data_root)
        records.write_reports(output_dir / "stage2")
        print("\nStage 2 preparation: source record assembly")
        print(records.summary.to_string(index=False))
        print(f"Source record reports: {output_dir / 'stage2'}")
        if args.resolve_identities:
            from plastprior.identity import resolve_identities

            print("\nStage 2: chemical identity resolution and aggregation", flush=True)
            identities = resolve_identities(records, args.data_root)
            identities.write_reports(output_dir / "stage2")
            print(identities.summary.to_string(index=False))
            print(identities.manifest["counts"])
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
