@echo off
rem Startet die Anwendung im Browser (siehe LIESMICH.txt).
cd /d "%~dp0"
where py >nul 2>nul && (py -3 start.py & goto :eof)
where python >nul 2>nul && (python start.py & goto :eof)
echo Python 3 fehlt: https://www.python.org/downloads/
pause
