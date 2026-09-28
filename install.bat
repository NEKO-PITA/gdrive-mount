@echo off
chcp 65001 >nul

echo ========================================
echo  GDrive Mount - Dependency Installation
echo ========================================
echo.

pushd "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.10+
    pause
    popd
    exit /b 1
)

echo [1/3] Creating virtual environment...
if not exist venv (
    python -m venv venv
)

if errorlevel 1 (
    echo [ERROR] Failed to create venv
    pause
    popd
    exit /b 1
)

echo [2/3] Installing requirements...
call venv\Scripts\activate.bat

if exist gdrive_mount\requirements.txt (
    pip install -r gdrive_mount\requirements.txt
) else if exist requirements.txt (
    pip install -r requirements.txt
) else (
    echo [WARNING] requirements.txt not found!
)

if errorlevel 1 (
    echo [ERROR] Failed to install requirements
    pause
    popd
    exit /b 1
)

echo [3/3] Installing PyInstaller...
pip install pyinstaller

echo.
echo ========================================
echo  Installation completed!
echo ========================================
echo.
echo  To run the app:
echo    .\venv\Scripts\python.exe gdrive_mount_app.py
echo.

popd
pause
exit /b 0
