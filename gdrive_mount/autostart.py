"""
Управление автозапуском приложения при входе в Windows.
Добавляет/удаляет ключ в реестре HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
"""

import sys
import os
import logging
import winreg

logger = logging.getLogger(__name__)

APP_NAME = "GDriveMount"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_exe_command() -> str:
    """
    Определяет команду для автозапуска.
    Если приложение скомпилировано PyInstaller — путь к .exe.
    Если запущено как скрипт — pythonw.exe + путь к скрипту.
    """
    if getattr(sys, 'frozen', False):
        # Скомпилировано PyInstaller
        return f'"{sys.executable}" --silent'
    else:
        # Запущено как Python-скрипт
        script = os.path.abspath(sys.argv[0])
        python_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(python_dir, "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable
        return f'"{pythonw}" "{script}" --silent'


def enable_autostart():
    """Добавляет приложение в автозапуск Windows."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH,
            0, winreg.KEY_SET_VALUE
        )
        command = _get_exe_command()
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        logger.info("Автозапуск включён: %s", command)
        return True
    except OSError as e:
        logger.error("Ошибка включения автозапуска: %s", e)
        return False


def disable_autostart():
    """Удаляет приложение из автозапуска Windows."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH,
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        logger.info("Автозапуск отключён")
        return True
    except FileNotFoundError:
        logger.info("Ключ автозапуска не найден (уже отключён)")
        return True
    except OSError as e:
        logger.error("Ошибка отключения автозапуска: %s", e)
        return False


def is_autostart_enabled() -> bool:
    """Проверяет, включён ли автозапуск."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH,
            0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def update_autostart_command():
    """
    Обновляет команду автозапуска (полезно после обновления приложения
    или изменения расположения).
    """
    if is_autostart_enabled():
        enable_autostart()
