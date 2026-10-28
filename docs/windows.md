# Run on native Windows

These steps run the Python analysis in Windows Command Prompt or PowerShell.
WSL, administrator rights for symlinks, R and Node.js are not required for this
analysis. Manuscript figure/PPT rendering is a separate workflow.

## Install once

Install **64-bit Python 3.12**, including its `py` launcher, and **Git for Windows**.
Open a new terminal after installation. From a writable parent directory:

```text
git clone https://github.com/ALECUnimelb/PlastPrior.git
cd PlastPrior
.\setup_windows.cmd
```

Use a reasonably short project path, such as `C:\Research\PlastPrior`.
The setup script creates `.venv`, installs the pinned direct dependencies, checks
RDKit InChI support, and registers the Jupyter kernel. Internet access is needed
for installation, including the pinned GIC Git dependency. No activation script
or PowerShell execution-policy change is needed. An existing environment must
also use 64-bit Python 3.12; the script stops if it does not.

## Add the frozen data and run

Extract the supplied data package with this layout (avoid `data\data\`):

```text
PlastPrior\
  main.py
  run_windows.cmd
  data\
    SourceDatabase\
    Vega output\
    GIC Regulatory Inventory\
    Patent data\
    Literature data\
    Official_Production_Volume_Data\
    ExposureReference\
      20261006T233429Z\
```

Preserve the filenames and original file bytes. The full checklist is in
[data preparation](data_preparation.md). Older backup trees in the full local
collection contain long paths. If extraction fails on those backup entries,
request a package containing the declared inputs; do not shorten paths referenced
by the required manifests. Then run:

```text
.\run_windows.cmd
```

For data kept outside the checkout, quote its path:

```text
.\run_windows.cmd --data-root "D:\Research data\PlastPrior inputs"
```

The launcher runs input inspection, all prerequisite analysis stages, Top-100
ranking including boundary ties, and verified export. It uses UTF-8 for Python
text I/O and console output. It does not modify the input package.
Do not run a separate inspection-only command first: partial runs retain
`.result-work`, and a subsequent run refuses to overwrite that workspace.

The three current deliverables are installed together in the real `result`
directory, without a symlink:

```text
result\PlastPrior_results.csv
result\PlastPrior_results.sqlite
result\PlastPrior_dashboard.sqlite
```

Metadata and supporting files are under `result\figure_data`. A successful run
removes temporary staging. Close result files in Excel, SQLite browsers and other
readers before replacing an existing result set. Only one analysis may update
the same checkout at a time. Existing results with dependent figures require a
coordinated figure-data refresh; this safeguard also applies on Windows.

## Notebook alternative

After setup, launch Jupyter with the project interpreter:

```text
.\.venv\Scripts\python.exe -X utf8 -m jupyterlab
```

Open `PlastPrior.ipynb`, select **PlastPrior (Python 3.12)**, set `DATA_ROOT` if
needed, restart the kernel and run all cells. Run either the Notebook or CLI,
not both concurrently.

## If a run stops

- **Missing input / fingerprint mismatch:** check the exact supplied package,
  filenames and nesting. Do not substitute newer files or edit expected hashes.
- **Previous or active work exists:** confirm no run is active and inspect
  `.result-work`. It is deliberately retained after a failure or partial run.
  After diagnosis, remove only that temporary workspace before restarting;
  preserve `data` and the last complete `result`.
- **PermissionError / WinError 32 or 5:** close programs using the result files
  and check write permission. Normal handled replacement failures preserve or
  restore the previous complete result. If a process or machine was interrupted
  and `.result-previous` remains, keep it for recovery rather than deleting it.
- **Dependency installation failure:** retain the entire terminal error, plus
  `py -3.12 --version` and `git --version`. Do not replace the pinned GIC dependency
  with the unrelated PyPI package named `gic`.

## Validation status

The repository includes native Windows, macOS and Linux CI jobs for dependency
installation and the fixture-based tests. The Windows job also exercises both
`.cmd` entry points. These jobs run once this change is published to GitHub;
their presence alone is not evidence of a passing Windows run. A full run using
the separately supplied research data is still needed on the colleague's PC.
Fixture tests can also be run locally without the research data:

```text
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

The local macOS verification of this change passed all 256 tests, including
database-handle cleanup, paths containing spaces/Unicode/URI-reserved characters,
UTF-8 CSV preservation, and rollback after a simulated Windows sharing violation.
This is not a native Windows execution result.
