@echo off
setlocal
cd /d "%~dp0"
if not exist "run-windows.bat.new" goto run
if exist "run-windows.bat" del /q "run-windows.bat"
move /y "run-windows.bat.new" "run-windows.bat" >nul 2>nul
:run
if not exist "run-windows.bat" goto missing
call "run-windows.bat"
exit /b %errorlevel%
:missing
echo [ERROR] run-windows.bat is missing from this folder.
pause
exit /b 1
