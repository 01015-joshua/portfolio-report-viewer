@echo off
setlocal
set "PYTHONUTF8=1"
pushd "%~dp0"
if errorlevel 1 goto folder_error
if not exist "requirements.txt" goto incomplete
if exist ".venv\Scripts\python.exe" goto dependencies
py -3 -c "import sys; sys.exit(sys.version_info[:2] < (3,11))" >nul 2>nul
if errorlevel 1 goto try_python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:try_python
python -c "import sys; sys.exit(sys.version_info[:2] < (3,11))" >nul 2>nul
if errorlevel 1 goto no_python
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] < (3,11))"
if errorlevel 1 goto no_python
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click start.cmd to open the app.
popd
pause
exit /b 0
:no_python
echo Python 3.11 or newer was not found.
echo Install Python and enable Add Python to PATH, then try again.
goto failed
:incomplete
echo requirements.txt was not found.
echo Extract the entire project ZIP first. Keep setup.cmd in the project folder.
goto failed
:folder_error
echo Cannot open the project folder.
pause
exit /b 1
:failed
echo.
echo Setup failed. Please send a screenshot of this entire window.
popd
pause
exit /b 1
