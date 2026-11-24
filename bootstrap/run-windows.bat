@echo off
setlocal enabledelayedexpansion
rem This script may live in <root>\bootstrap (dev) or directly in <root> (guided deploy).
rem Locate the folder that actually contains requirements.txt and make it the base.
set "BASE=%~dp0"
:findbase
if exist "%BASE%requirements.txt" goto base_ok
for %%P in ("%BASE%..\") do set "UP=%%~fP"
if /i "%UP%"=="%BASE:~0,-1%" goto base_missing
set "BASE=%UP%"
goto findbase
:base_ok
cd /d "%BASE%"
rem Miniconda installer rejects non-ASCII install paths (e.g. Chinese folder names).
rem Use exit code only (no output parsing) to avoid quoting pitfalls.
set "CSD_CUR=%CD%"
powershell -NoProfile -Command "if ($env:CSD_CUR -match '[\u0080-\uFFFF]') { exit 1 } else { exit 0 }"
if errorlevel 1 goto non_ascii_path
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

set "PY=.runtime\python.exe"
set "MC=Miniconda3-py312_26.9.4-1-Windows-x86_64.exe"

if exist "%PY%" goto have_runtime

echo.
echo [1/5] Preparing a private Python runtime (one time, about 90 MB)
echo        From Chinese mirrors - no VPN needed. You do NOT need Python installed.
if not exist ".runtime" mkdir ".runtime"

where curl >nul 2>nul
if errorlevel 1 goto no_curl
echo        Downloading from TUNA mirror ...
curl -fL --retry 2 -o "%MC%" "https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/%MC%"
if not errorlevel 1 goto unpack
if exist "%MC%" del /q "%MC%"
echo        TUNA failed, trying Huawei Cloud ...
curl -fL --retry 2 -o "%MC%" "https://mirrors.huaweicloud.com/anaconda/miniconda/%MC%"
if not errorlevel 1 goto unpack
if exist "%MC%" del /q "%MC%"
goto download_failed

:unpack
echo [2/5] Installing Python into .runtime (silent, nothing system-wide) ...
rem JustMe + RegisterPython=0 + no PATH: nothing is written system-wide. /D must be last, no quotes.
"%MC%" /InstallationType=JustMe /RegisterPython=0 /S /D=%CD%\.runtime
if errorlevel 1 goto unpack_failed
if exist "%MC%" del /q "%MC%"

:have_runtime
if not exist "%PY%" goto runtime_missing

:install_deps
echo [3/5] Installing components into the private runtime (first run only)
echo        All packages go into .runtime - nothing is written to the system Python.
set "PIPFLAGS=--disable-pip-version-check --no-warn-script-location --no-cache-dir --timeout 20 --retries 2"
rem Try several indexes; any one succeeding is enough. Official last.
call :try_pip "https://pypi.tuna.tsinghua.edu.cn/simple"
if not errorlevel 1 goto check_native
call :try_pip "https://mirrors.aliyun.com/pypi/simple/"
if not errorlevel 1 goto check_native
call :try_pip "https://pypi.doubanio.com/simple/"
if not errorlevel 1 goto check_native
call :try_pip ""
if errorlevel 1 goto pip_failed
goto check_native

:try_pip
echo        pip index: %~1
if "%~1"=="" (
  "%PY%" -m pip install %PIPFLAGS% -r requirements.txt
) else (
  "%PY%" -m pip install %PIPFLAGS% -r requirements.txt -i %~1
)
exit /b %errorlevel%

:check_native
echo [4/5] Checking native deps ...
"%PY%" -c "import cv2, numpy, pymupdf; print('core ok')"
if errorlevel 1 goto native_failed

echo [5/5] Preparing MolDet model weight (first run downloads ~50 MB) ...
if exist "fetch_models.py" goto fetch_here
if exist "bootstrap\fetch_models.py" goto fetch_sub
echo [WARN] fetch_models.py not found; skipping MolDet weight check.
goto after_fetch
:fetch_here
"%PY%" fetch_models.py
if errorlevel 1 goto model_failed
goto after_fetch
:fetch_sub
"%PY%" bootstrap\fetch_models.py
if errorlevel 1 goto model_failed
:after_fetch

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

:restart
echo Backend requested restart ...
start "" "%~dp0start-windows.bat"
exit /b 0

:base_missing
echo [ERROR] requirements.txt not found above this folder. Put the launcher in the folder with requirements.txt.
pause
exit /b 1
:non_ascii_path
echo [ERROR] The folder path contains non-ASCII characters (e.g. Chinese).
echo         The Python installer cannot install into such a path.
echo.
echo         Current path: %CD%
echo         Please rename the folder to use English letters only (e.g. CSD),
echo         or move it to an English path like C:\CSD, then run again.
pause
exit /b 1
:download_failed
echo [ERROR] Cannot download Python runtime from TUNA or Huawei Cloud mirrors.
echo         Check your network connection to Chinese mirrors.
pause
exit /b 1
:no_curl
echo [ERROR] curl.exe not found. Need Windows 10 1803+ (curl is built in).
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
:model_failed
echo [ERROR] MolDet weight download failed. See message above.
pause
exit /b 1
:backend_failed
echo [ERROR] Backend exited with an error.
pause
exit /b 1
