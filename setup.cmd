@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (python -m venv .venv) else (py -3 -m venv .venv)
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo 初期設定が完了しました。start.cmd を実行してください。
pause
exit /b 0
:failed
echo 初期設定に失敗しました。Python 3.11以降が必要です。README.md をご確認ください。
pause
exit /b 1
