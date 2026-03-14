@echo off
set PYTHON_HOME=%LocalAppData%\Programs\Python\Python313
if exist "%PYTHON_HOME%\python.exe" (
  "%PYTHON_HOME%\python.exe" "%~dp0web_server.py"
) else (
  python "%~dp0web_server.py"
)
