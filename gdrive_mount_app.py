#!/usr/bin/env python3
"""
GDrive Mount — точка входа.
Монтирует Google Drive как локальный диск Windows 
с автозапуском и системным треем.

Использование:
    python gdrive_mount_app.py              # Обычный запуск (с GUI настройки)
    python gdrive_mount_app.py --silent     # Тихий запуск (для автозагрузки)
    python gdrive_mount_app.py --reset      # Сброс настроек
"""

import sys
import os
import argparse
import ctypes
import logging


def is_already_running() -> bool:
    """
    Проверяет, не запущен ли уже экземпляр приложения.
    Использует именованный мьютекс Windows.
    """
    try:
        mutex_name = "Global\\GDriveMountMutex"
        mutex = ctypes.windll.kernel32.CreateMutexW(None, True, mutex_name)
        last_error = ctypes.windll.kernel32.GetLastError()
        # ERROR_ALREADY_EXISTS = 183
        if last_error == 183:
            ctypes.windll.kernel32.CloseHandle(mutex)
            return True
        return False
    except Exception:
        return False


def hide_console():
    """Скрывает консольное окно (для pythonw.exe это не нужно)."""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="GDrive Mount — Google Drive как локальный диск Windows"
    )
    parser.add_argument(
        "--silent", action="store_true",
        help="Тихий запуск (без мастера настройки, для автозагрузки)"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Сброс настроек и повторная настройка"
    )
    parser.add_argument(
        "--no-mount", action="store_true",
        help="Не монтировать диск автоматически"
    )
    parser.add_argument(
        "--drive-letter", type=str, default=None,
        help="Буква диска (например: G)"
    )

    args = parser.parse_args()

    # Проверяем, не запущен ли уже
    if is_already_running():
        print("GDrive Mount уже запущен.")
        if not args.silent:
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "GDrive Mount уже запущен.\n"
                    "Проверьте иконку в системном трее (🔽 в панели задач).",
                    "GDrive Mount",
                    0x40  # MB_ICONINFORMATION
                )
            except Exception:
                pass
        sys.exit(0)

    # Скрываем консоль при тихом запуске
    if args.silent:
        hide_console()

    # Импортируем приложение
    from gdrive_mount.app import GDriveMountApp
    from gdrive_mount.config import Config

    # Сброс настроек
    if args.reset:
        config = Config()
        config.configured = False
        print("Настройки сброшены. Запуск мастера настройки...")

    # Создаём и запускаем приложение
    app = GDriveMountApp(silent=args.silent)

    # Переопределяем букву диска из аргументов
    if args.drive_letter:
        app.config.drive_letter = args.drive_letter

    try:
        app.run()
    except KeyboardInterrupt:
        print("\nЗавершение по Ctrl+C...")
        app.cleanup()
    except Exception as e:
        logging.exception("Критическая ошибка: %s", e)
        if not args.silent:
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Произошла ошибка:\n{e}\n\n"
                f"Подробности в логах:\n{app.config.app_log_file}",
                "GDrive Mount — Ошибка",
                0x10  # MB_ICONERROR
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
