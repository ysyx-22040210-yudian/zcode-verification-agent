@echo off
"%~dp0formal-toolchain\python\python.exe" -E -s -X utf8 "%~dp0portable.py" %*
exit /b %errorlevel%

