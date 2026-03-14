@echo off
set PYTHON_HOME=%LocalAppData%\Programs\Python\Python313
if exist "%PYTHON_HOME%\python.exe" (
  "%PYTHON_HOME%\python.exe" "%~dp0app.py"
) else (
  python "%~dp0app.py"
)
