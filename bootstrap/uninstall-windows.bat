@echo off
setlocal
cd /d "%~dp0.."

echo ============================================
echo  CSD - remove ALL local files
echo  This deletes: .runtime, pycache, data, training outputs
echo  Nothing outside this folder was ever written by CSD.
echo ============================================
echo.

set /p "CONFIRM=Type YES to delete everything in this folder's runtime/data: "
if /i not "%CONFIRM%"=="YES" (
  echo Cancelled. Nothing removed.
  pause
  exit /b 0
)

if exist ".runtime" (
  echo Removing .runtime ...
  rmdir /s /q ".runtime"
)
if exist "data" (
  echo Removing data ...
  rmdir /s /q "data"
)
if exist "training" (
  echo Removing training outputs ...
  rmdir /s /q "training\01-collect" 2>nul
  rmdir /s /q "training\02-topo" 2>nul
  rmdir /s /q "training\03-style" 2>nul
  rmdir /s /q "training\04-render" 2>nul
  rmdir /s /q "training\05-match" 2>nul
  rmdir /s /q "training\models" 2>nul
  rmdir /s /q "training\templates" 2>nul
  rmdir /s /q "training\render_cache" 2>nul
)
echo.
echo Done. All CSD runtime and data removed.
echo The source code and bootstrap scripts remain (that is your copy of the app).
pause
exit /b 0
