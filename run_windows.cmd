@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Run setup_windows.cmd first.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 main.py --rank-priority --top-n 100 --require-supporting-inputs --output-dir result %*
set "plastprior_exit_code=%errorlevel%"
if not "%plastprior_exit_code%"=="0" echo Analysis failed. Keep the error text and temporary workspace for diagnosis.
popd
exit /b %plastprior_exit_code%
