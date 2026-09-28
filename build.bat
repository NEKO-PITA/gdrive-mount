@echo off
chcp 65001 >nul
echo ========================================
echo  GDrive Mount - Building .exe
echo ========================================
echo.

pushd "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo [ERROR] Virtual environment not found. Run install.bat first!
    pause
    popd
    exit /b 1
)

echo [1/2] Activating environment and checking PyInstaller...
call venv\Scripts\activate.bat

python -m pip install pyinstaller

echo [2/2] Running PyInstaller compilation...
python -m PyInstaller --onefile --windowed --name GDriveMount --add-data "gdrive_mount;gdrive_mount" --hidden-import pystray._win32 --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFont gdrive_mount_app.py

if errorlevel 1 (
    echo [ERROR] Build failed!
    pause
    popd
    exit /b 1
)

echo.
echo ========================================
echo  Done! File saved to: dist\GDriveMount.exe
echo ========================================
echo.

popd
pause
exit /b 0

