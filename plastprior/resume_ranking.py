"""Resume a run that stopped before Stage 7B, without recalculating Stages 1–7A."""
import argparse
from pathlib import Path

from .delivery import finish_run
from .export import _inventory
from .ranking import integrate_ranking
from .result_storage import update_lock, validate_destination


def resume_ranking(workspace, destination, *, top_n=100, strict_historical=False,
                   keep_intermediates=False, progress=print):
    workspace = Path(workspace).expanduser().resolve()
    destination = validate_destination(Path(destination).expanduser().resolve())
    if (workspace == destination or workspace.is_relative_to(destination)
            or destination.is_relative_to(workspace)):
        raise ValueError('The result directory and temporary workspace must be separate.')
    work = workspace / 'work'
    if not (work / 'stage7' / '7a' / 'priority_manifest.json').is_file():
        raise FileNotFoundError('Completed Stage 7A not found in ' + str(work))
    with update_lock(workspace):
        if (workspace / 'package').exists() or (work / 'stage7' / '7b').exists():
            raise FileExistsError('Stage 7B or an export package already exists. Preserve and inspect it before retrying; this command resumes runs stopped before Stage 7B output.')
        progress('Verifying all retained stage files and upstream manifest links through Stage 7A.')
        _inventory(work, include_ranking=False)
        rankings = integrate_ranking(work / 'stage7' / '7a', top_n,
                                     strict_historical=strict_historical)
        rankings.write_reports(work / 'stage7' / '7b')
        progress('Stage 7B complete; historical ordering mode: ' + rankings.manifest['historical_order']['mode'])
        return finish_run(work, destination, workspace,
                          keep_intermediates=keep_intermediates, progress=progress)


def main(argv=None):
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path('.result-work'))
    parser.add_argument('--output-dir', type=Path, default=Path('result'))
    parser.add_argument('--top-n', type=int, default=100)
    parser.add_argument('--strict-historical', action='store_true')
    parser.add_argument('--keep-intermediates', action='store_true')
    args = parser.parse_args(argv)
    def resolve(path):
        path = path.expanduser()
        return path if path.is_absolute() else project / path
    package = resume_ranking(resolve(args.workspace), resolve(args.output_dir),
                             top_n=args.top_n, strict_historical=args.strict_historical,
                             keep_intermediates=args.keep_intermediates)
    for key in ('csv', 'sqlite', 'dashboard_sqlite'):
        print(f'{key}: {package[key]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
