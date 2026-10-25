"""Run staged chemical evidence, hazard, exposure and priority assessment."""

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
                        help="Daily two-file directory (default: results); stages go to the audit archive.")
    parser.add_argument("--assemble-records", action="store_true",
                        help="Also assemble source inventory records; no identity resolution or deduplication.")
    parser.add_argument("--resolve-identities", action="store_true",
                        help="Assemble records, resolve structures and aggregate by full InChIKey.")
    parser.add_argument("--integrate-qsar", action="store_true",
                        help="Also screen structures and integrate the frozen VEGA batch; no Pov/LRTP or scoring.")
    parser.add_argument("--calculate-lrtp", action="store_true",
                        help="Also calculate Pov/LRTP and isolate unverified identities; no downstream scoring.")
    parser.add_argument("--integrate-evidence", action="store_true",
                        help="Also assemble basic source evidence (4A); no specialist enrichment or scoring.")
    parser.add_argument("--integrate-specialists", action="store_true",
                        help="Also integrate LitChemPlast and FCChumon evidence (4B); no 4C or scoring.")
    parser.add_argument("--integrate-annotations", action="store_true",
                        help="Also attach NORMAN and GIC annotations (4C); no downstream scoring.")
    parser.add_argument("--assess-pm", action="store_true",
                        help="Also assess persistence and mobility (5A); no B/T, exposure or prioritisation.")
    parser.add_argument("--assess-bt", action="store_true",
                        help="Also assess bioaccumulation and toxicity (5B); no aggregate hazard, exposure or priority scores.")
    parser.add_argument("--audit-exposure", action="store_true",
                        help="Also audit frozen exposure evidence and eligibility (6A); no exposure or priority scores.")
    parser.add_argument("--assess-exposure", action="store_true",
                        help="Also score exposure dimensions (6B), retaining missingness and historical results; no prioritisation or ranking.")
    parser.add_argument("--assess-priority", action="store_true",
                        help="Also assess aggregate scores, completeness and tiers (7A); no ranking or Top-N.")
    parser.add_argument("--rank-priority", action="store_true",
                        help="Also generate eligible competition ranks and inclusive Top-N (7B).")
    parser.add_argument("--top-n", type=int, default=100,
                        help="Requested eligible Top-N size; boundary ties are included (default: 100).")
    parser.add_argument("--archive-dir", type=Path, default=Path("audit_archive"),
                        help="Separate run archives and temporary stages.")
    parser.add_argument("--keep-intermediates", action="store_true",
                        help="Keep successful stage files; failed or partial runs always retain them.")
    parser.add_argument("--baseline-csv", type=Path,
                        help="Require all existing publication values to match this CSV before publishing.")
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be positive")
    if args.rank_priority:
        args.assess_priority = True
    if args.assess_priority:
        args.assess_exposure = True
    if args.assess_exposure:
        args.audit_exposure = True
    if args.audit_exposure:
        args.assess_bt = True
    if args.assess_bt:
        args.assess_pm = True
    if args.assess_pm:
        args.integrate_annotations = True
    if args.integrate_annotations:
        args.integrate_specialists = True
    if args.integrate_specialists:
        args.integrate_evidence = True
    print("Inspecting source files and supporting input presence...", flush=True)
    report = inspect_inputs(args.data_root)
    for title, frame in (("Source files", report.sources[["source", "version", "status", "detail"]]),
                         ("Source-native tables", report.tables),
                         ("Supporting inputs (presence only)", report.supporting)):
        print(f"\n{title}\n{frame.to_string(index=False)}")
    from plastprior.delivery import new_workspace
    project = Path(__file__).resolve().parent
    daily_dir = args.output_dir.expanduser()
    daily_dir = daily_dir if daily_dir.is_absolute() else project / daily_dir
    archive_dir = args.archive_dir.expanduser()
    archive_dir = archive_dir if archive_dir.is_absolute() else project / archive_dir
    if archive_dir.absolute() == daily_dir.absolute() or archive_dir.absolute().is_relative_to(daily_dir.absolute()):
        parser.error("--archive-dir must be outside --output-dir")
    output_dir = new_workspace(archive_dir)
    print(f"Run workspace (retained on failure): {output_dir}", flush=True)
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
    if passed and (args.assemble_records or args.resolve_identities or args.integrate_qsar or args.calculate_lrtp or args.integrate_evidence):
        records = build_source_records(args.data_root)
        records.write_reports(output_dir / "stage2")
        print("\nStage 2 preparation: source record assembly")
        print(records.summary.to_string(index=False))
        print(f"Source record reports: {output_dir / 'stage2'}")
        if args.resolve_identities or args.integrate_qsar or args.calculate_lrtp or args.integrate_evidence:
            from plastprior.identity import resolve_identities

            print("\nStage 2: chemical identity resolution and aggregation", flush=True)
            identities = resolve_identities(records, args.data_root)
            identities.write_reports(output_dir / "stage2")
            print(identities.summary.to_string(index=False))
            print(identities.manifest["counts"])
            if args.integrate_qsar or args.calculate_lrtp or args.integrate_evidence:
                from plastprior.qsar import integrate_qsar

                print("\nStage 3A: frozen QSAR evidence integration", flush=True)
                qsar = integrate_qsar(identities, args.data_root)
                qsar.write_reports(output_dir / "stage3")
                print(qsar.manifest["counts"])
                print("Identity-review associations remain unverified; consult the audit reports.")
                if args.calculate_lrtp or args.integrate_evidence:
                    from plastprior.lrtp import integrate_lrtp

                    print("\nStage 3B: Pov/LRTP calculation and identity isolation", flush=True)
                    lrtp = integrate_lrtp(output_dir / "stage3")
                    lrtp.write_reports(output_dir / "stage3" / "lrtp")
                    print(lrtp.manifest["counts"])
                    print("Historical reproduction is separate from analysis availability; no scoring was performed.")
                    if args.integrate_evidence:
                        from plastprior.evidence import integrate_evidence

                        print("\nStage 4A: basic evidence assembly and prediction isolation", flush=True)
                        evidence = integrate_evidence(output_dir / "stage2", output_dir / "stage3" / "lrtp", args.data_root)
                        evidence.write_reports(output_dir / "stage4")
                        print(evidence.manifest["counts"])
                        print("Basic evidence complete. Specialist enrichment and downstream scoring are not performed.")
                        if args.integrate_specialists:
                            from plastprior.evidence_specialists import integrate_specialist_evidence

                            print("\nStage 4B: literature associations and human detection evidence", flush=True)
                            specialists = integrate_specialist_evidence(output_dir / "stage2", output_dir / "stage4", args.data_root)
                            specialists.write_reports(output_dir / "stage4" / "4b")
                            print(specialists.manifest["counts"])
                            print("Stage 4B complete. Model identity exclusions remain in effect.")
                            if args.integrate_annotations:
                                from plastprior.evidence_annotations import integrate_annotations

                                print("\nStage 4C: analytical-platform and regulatory-list annotations", flush=True)
                                annotations = integrate_annotations(output_dir / "stage4" / "4b", args.data_root)
                                annotations.write_reports(output_dir / "stage4" / "4c")
                                print(annotations.manifest["counts"])
                                print("Name associations require review; model exclusions remain in effect. No scoring performed.")
    if passed and args.assess_pm:
        from plastprior.hazard import integrate_pm_hazard

        print("\nStage 5A: persistence and mobility with identity isolation", flush=True)
        hazard = integrate_pm_hazard(output_dir / "stage4" / "4c")
        hazard.write_reports(output_dir / "stage5")
        print(hazard.summary.to_string(index=False))
        print("Historical reproduction is separate from eligible analysis. GIC annotations do not enter scoring.")
    if passed and args.assess_bt:
        from plastprior.hazard_bt import integrate_bt_hazard

        print("\nStage 5B: bioaccumulation and toxicity with identity isolation", flush=True)
        hazard_bt = integrate_bt_hazard(output_dir / "stage5")
        hazard_bt.write_reports(output_dir / "stage5" / "5b")
        print(hazard_bt.summary.to_string(index=False))
        print("Independent structure and curated evidence remain eligible. No aggregate scores calculated.")
    if passed and args.audit_exposure:
        from plastprior.exposure_inputs import integrate_exposure_evidence

        print("\nStage 6A: exposure evidence intake and eligibility audit", flush=True)
        exposure = integrate_exposure_evidence(output_dir / "stage5" / "5b", args.data_root)
        exposure.write_reports(output_dir / "stage6" / "6a")
        print(exposure.summary.to_string(index=False))
        print("Frozen inputs and identity gates audited. No exposure scores or numeric maxima calculated.")
    if passed and args.assess_exposure:
        from plastprior.exposure import integrate_exposure_scores

        print("\nStage 6B: exposure dimension assessment with eligibility audit", flush=True)
        exposure_scores = integrate_exposure_scores(output_dir / "stage6" / "6a", args.data_root)
        exposure_scores.write_reports(output_dir / "stage6" / "6b")
        print(exposure_scores.summary.to_string(index=False))
        print("Exposure totals sum available contributions; completeness is reported separately. No combined priority or ranking calculated.")
    if passed and args.assess_priority:
        from plastprior.priority import integrate_priority

        print("\nStage 7A: aggregate scores, completeness and tier audit", flush=True)
        priority = integrate_priority(output_dir / "stage6" / "6b")
        priority.write_reports(output_dir / "stage7" / "7a")
        print(priority.summary.to_string(index=False))
        print("Missing components contribute zero to sums and retain missingness reasons. No ranking or Top-N generated.")
    if passed and args.rank_priority:
        from plastprior.ranking import integrate_ranking

        print("\nStage 7B: eligible competition ranks and inclusive Top-N", flush=True)
        rankings = integrate_ranking(output_dir / "stage7" / "7a", args.top_n)
        rankings.write_reports(output_dir / "stage7" / "7b")
        print(rankings.summary)
        print("Only records with no available evidence retain null ranks. Identifier order only stabilises the display of ties.")
        from plastprior.delivery import finish_run

        package = finish_run(output_dir, daily_dir, archive_dir,
                             keep_intermediates=args.keep_intermediates,
                             baseline_csv=args.baseline_csv,
                             progress=lambda message: print(message, flush=True))
        print(f"Daily CSV: {daily_dir / 'PlastPrior_results.csv'}")
        print(f"Daily SQLite: {daily_dir / 'PlastPrior_dashboard.sqlite'}")
        print(f"Complete audit archive: {package['directory']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
