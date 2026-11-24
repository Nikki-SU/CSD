@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."
rem Keep everything inside this folder: no pip cache, no __pycache__, no system writes.
set "PYTHONDONTWRITEBYTECODE=1"
set "PIP_NO_CACHE_DIR=1"
set "PYTHONPYCACHEPREFIX=%CD%\.runtime\pycache"

echo ============================================
echo  CSD local backend - first run sets up everything
echo  ISOLATED: Python and all packages live in .runtime\
echo            Nothing is installed system-wide. Delete the folder to remove all.
echo  Backend: http://127.0.0.1:8765
echo ============================================

set "PYTAG=20261026"
set "PYVER=3.12.16"
set "GHBASE=https://github.com/astral-sh/python-build-standalone/releases/download/%PYTAG%"
set "PKG=cpython-%PYVER%+%PYTAG%-x86_64-pc-windows-msvc-install_only.tar.gz"
set "SHA=590dfcbe3a34c07301e6332e13e2188b98655cd072b08afa45a7998dc4c22bc5"
set "PY=.runtime\python.exe"

if exist "%PY%" goto have_runtime

echo.
echo [1/4] Preparing a private Python runtime (one time, about 50 MB)
echo        You do NOT need Python installed on this computer.
if not exist ".runtime" mkdir ".runtime"

call :try_download "%GHBASE%/%PKG%"
if not errorlevel 1 goto unpack
call :try_download "https://gh-proxy.com/%GHBASE%/%PKG%"
if not errorlevel 1 goto unpack
call :try_download "https://ghproxy.net/%GHBASE%/%PKG%"
if not errorlevel 1 goto unpack
goto download_failed

:unpack
echo [2/4] Unpacking runtime ...
where tar >nul 2>nul
if errorlevel 1 goto no_tar
tar -xzf "python-runtime.tar.gz" -C ".runtime" --strip-components=1
if errorlevel 1 goto unpack_failed
del /q "python-runtime.tar.gz"

:have_runtime
if not exist "%PY%" goto runtime_missing

:install_deps
echo [3/4] Installing components into the private runtime (first run only)
echo        All packages go into .runtime - nothing is written to the system Python.
set "PIPFLAGS=--disable-pip-version-check --no-warn-script-location --no-cache-dir --timeout 20 --retries 2"
"%PY%" -m pip install %PIPFLAGS% -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if not errorlevel 1 goto check_native
echo        Mirror failed, retrying with the official index ...
"%PY%" -m pip install %PIPFLAGS% -r requirements.txt
if errorlevel 1 goto pip_failed

:check_native
echo [4/4] Checking native deps ...
"%PY%" -c "import cv2, numpy, pymupdf; print('core ok')"
if errorlevel 1 goto native_failed

if defined CSD_DATA_DIR (
  echo Data dir: %CSD_DATA_DIR%
) else (
  echo Data dir: ^(default^) ./data
)

echo.
echo Starting backend ... Keep this window open. Close it to stop the server.
echo.
"%PY%" -m backend.server
if errorlevel 86 goto restart
if errorlevel 1 goto backend_failed
exit /b 0

:try_download
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%~1' -OutFile 'python-runtime.tar.gz' -TimeoutSec 120"
if errorlevel 1 exit /b 1
for /f %%a in ('powershell -NoProfile -Command "(Get-FileHash 'python-runtime.tar.gz' -Algorithm SHA256).Hash.ToLower()"') do set "GOT=%%a"
if /i not "%GOT%"=="%SHA%" (
  echo   Hash mismatch, trying next source ...
  del /q "python-runtime.tar.gz"
  exit /b 1
)
exit /b 0

:restart
echo Backend requested restart ...
start "" "%~dp0start-windows.bat"
exit /b 0

:download_failed
echo [ERROR] Cannot download Python runtime. Check internet or VPN.
pause
exit /b 1
:no_tar
echo [ERROR] tar not found. Need Windows 10 1803+ or install bsdtar.
pause
exit /b 1
:unpack_failed
echo [ERROR] Failed to unpack Python runtime.
pause
exit /b 1
:runtime_missing
echo [ERROR] Python runtime missing at .runtime\python.exe.
pause
exit /b 1
:pip_failed
echo [ERROR] pip install failed. Check network, or use a different mirror.
pause
exit /b 1
:native_failed
echo [ERROR] Core deps failed to import. Try: pip install opencv-python pymupdf
pause
exit /b 1
:backend_failed
echo [ERROR] Backend exited with an error.
pause
exit /b 1
