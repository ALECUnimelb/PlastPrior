@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
where git >nul 2>nul
if errorlevel 1 (
    echo Install Git for Windows, then reopen your terminal and try again.
    goto failed
)
py -3.12 -c "import struct; assert struct.calcsize('P') == 8, '64-bit Python 3.12 is required'"
if errorlevel 1 (
    echo Install 64-bit Python 3.12 with the Python launcher enabled.
    goto failed
)
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import sys, struct; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8, 'Existing .venv must use 64-bit Python 3.12'"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 -c "from rdkit import Chem; assert Chem.MolToInchiKey(Chem.MolFromSmiles('CCO')) == 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N', 'RDKit InChI support is required'"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 -m ipykernel install --sys-prefix --name plastprior --display-name "PlastPrior (Python 3.12)"
if errorlevel 1 goto failed
echo Setup complete. Place the frozen inputs in data, then run run_windows.cmd.
popd
exit /b 0

:failed
echo Setup failed. See the error above; analysis has not been started.
popd
exit /b 1
