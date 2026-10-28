"""Replace one complete result directory without accumulating run versions."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import shutil
import tempfile


def validate_destination(destination):
    destination = Path(destination).absolute()
    project = Path(__file__).resolve().parents[1]
    if destination == project or (destination.is_relative_to(project) and destination != project/'result'):
        raise ValueError('Project results must be written to result; research inputs and source directories cannot be replaced.')
    return destination


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def update_lock(destination):
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name('.' + destination.name + '-update.lock')
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError(f'Result update already running or interrupted; inspect {lock}') from None
    try:
        yield
    finally:
        lock.rmdir()


def merge_existing(candidate, destination):
    """Keep current inputs and figures; block an uncoordinated database refresh.

Changing a data set with dependent figures requires a staged figure-data refresh,
not carrying old tables into a new data set. Layout-only work does not use this
database replacement path.
    """
    candidate, destination = Path(candidate), Path(destination)
    if not destination.exists():
        return
    if destination.is_symlink():
        raise ValueError('Result must be a real directory, not a version-selection link')
    dependencies = ('PlastPrior_results.csv', 'PlastPrior_results.sqlite',
                    'PlastPrior_dashboard.sqlite', 'figure_data/_metadata/scoring_config.json')
    changed = [name for name in dependencies
               if (destination/name).exists() and (candidate/name).exists()
               and sha(destination/name) != sha(candidate/name)]
    if (destination/'figures').exists() and changed:
        raise ValueError('Dependent figure data require a coordinated refresh before replacing result; current files are unchanged.')
    copy_missing(destination, candidate)


def copy_missing(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        dest = target/item.name
        if item.is_dir():
            copy_missing(item, dest)
        elif not dest.exists():
            shutil.copy2(item, dest)


def normalise_package(directory):
    """Keep the public result root limited to the agreed fixed deliverables."""
    directory = Path(directory)
    public = {'PlastPrior_results.csv','PlastPrior_results.sqlite',
              'PlastPrior_dashboard.sqlite','figure_data','figures','Figures.pptx'}
    decks = [p for p in directory.iterdir() if p.suffix.lower() == '.pptx' and not p.name.startswith('~$')]
    if len(decks) > 1: raise ValueError('Keep only one current presentation in result')
    public.update(p.name for p in decks)
    for item in list(directory.iterdir()):
        if item.name in public: continue
        if item.name == '.DS_Store':
            item.unlink(); continue
        if item.suffix == '.json':
            dest = directory/'figure_data/_metadata'/item.name
        elif item.name == 'score_chart_data.csv':
            dest = directory/'figure_data'/item.name
        else:
            dest = directory/'figure_data/_dependencies'/item.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists(): raise ValueError('Duplicate package entry: '+str(dest))
        shutil.move(str(item), dest)



def replace_directory(candidate, destination, validate=None):
    """Swap a validated directory with rollback and no retained prior version.

Call under update_lock. Readers must finish before this short replacement window.
An interrupted replacement leaves a fixed recovery directory; the next writer
refuses to overwrite it rather than silently losing the last complete result.
    """
    candidate, destination = Path(candidate), Path(destination).absolute()
    backup = destination.with_name('.' + destination.name + '-previous')
    if backup.exists():
        raise RuntimeError(f'Interrupted replacement requires recovery: {backup}')
    had_previous = destination.exists()
    try:
        if had_previous:
            os.replace(destination, backup)
        os.replace(candidate, destination)
        if validate is not None: validate()
    except BaseException:
        if backup.exists():
            if destination.exists(): shutil.rmtree(destination)
            os.replace(backup, destination)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def install_package(package, destination):
    """Install a validated complete package at the fixed current location."""
    destination = validate_destination(destination)
    with update_lock(destination):
        stage = Path(tempfile.mkdtemp(prefix='.result-building-', dir=destination.parent))
        try:
            shutil.copytree(package, stage, dirs_exist_ok=True)
            normalise_package(stage)
            merge_existing(stage, destination)
            normalise_package(stage)
            replace_directory(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
