"""
Главный модуль приложения GDriveMount.
Координирует все компоненты: rclone, трей, автозапуск, настройку.
"""

import sys
import logging
import threading
from pathlib import Path

from gdrive_mount.config import Config
from gdrive_mount.rclone import RcloneManager
from gdrive_mount.tray import TrayApp
from gdrive_mount import autostart

logger = logging.getLogger(__name__)


class GDriveMountApp:
    """
    Главное приложение GDriveMount.
    
    Жизненный цикл:
    1. Инициализация конфигурации
    2. Первоначальная настройка (если не настроено)
    3. Монтирование Google Drive
    4. Запуск системного трея
    """

    def __init__(self, silent: bool = False):
        """
        Args:
            silent: Если True — запуск без GUI (для автозапуска).
        """
        self.config = Config()
        self.rclone = RcloneManager(self.config)
        self.tray = TrayApp(self)
        self.silent = silent

        # Связываем callback монтирования с треем
        self.rclone.set_status_callback(self.tray.on_mount_status_changed)

        self._setup_logging()
        logger.info("=" * 50)
        logger.info("GDriveMount запущен (silent=%s)", silent)
        logger.info("Конфигурация: %s", self.config)

    def _setup_logging(self):
        """Настраивает логирование приложения."""
        log_file = self.config.app_log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Файловый обработчик
        file_handler = logging.FileHandler(
            str(log_file), encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))

        # Консольный обработчик (если не silent)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO if not self.silent else logging.WARNING)
        console_handler.setFormatter(logging.Formatter(
            "[%(levelname)s] %(message)s"
        ))

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    # ─── Первоначальная настройка ─────────────────────────────

    def run_setup(self) -> bool:
        """
        Запускает мастер первоначальной настройки.
        Возвращает True если настройка завершена успешно.
        """
        # Импортируем здесь, чтобы не грузить tkinter при обычном запуске
        from gdrive_mount.setup_wizard import SetupWizard

        wizard = SetupWizard(self)
        return wizard.run()

    # ─── Управление монтированием ─────────────────────────────

    def mount(self) -> bool:
        """Монтирует Google Drive."""
        return self.rclone.mount()

    def unmount(self) -> bool:
        """Размонтирует Google Drive."""
        return self.rclone.unmount()

    def is_mounted(self) -> bool:
        """Проверяет, смонтирован ли диск."""
        return self.rclone.is_mounted()

    def get_drive_info(self) -> dict | None:
        """Получает информацию о Google Drive."""
        return self.rclone.get_drive_info()

    # ─── Управление автозапуском ──────────────────────────────

    def enable_autostart(self) -> bool:
        """Включает автозапуск."""
        success = autostart.enable_autostart()
        if success:
            self.config.autostart_enabled = True
        return success

    def disable_autostart(self) -> bool:
        """Отключает автозапуск."""
        success = autostart.disable_autostart()
        if success:
            self.config.autostart_enabled = False
        return success

    def is_autostart_enabled(self) -> bool:
        """Проверяет, включён ли автозапуск."""
        return autostart.is_autostart_enabled()

    # ─── Перенастройка ────────────────────────────────────────

    def reconfigure(self) -> bool:
        """Пересоздаёт Google Drive remote (смена аккаунта)."""
        return self.rclone.reconfigure_remote()

    # ─── Запуск приложения ────────────────────────────────────

    def run(self):
        """
        Главный метод запуска приложения.
        
        Порядок действий:
        1. Если не настроено — запускает мастер настройки
        2. Монтирует Google Drive
        3. Запускает системный трей
        """
        # Шаг 1: Проверяем настройку
        if not self.config.configured or not self.rclone.is_remote_configured():
            logger.info("Первоначальная настройка не завершена")

            if self.silent:
                # При тихом запуске (автозагрузка) — показываем уведомление
                logger.warning(
                    "Приложение не настроено. Запустите без флага --silent."
                )
                # Всё равно запускаем трей, чтобы пользователь мог настроить
                self.tray.run()
                return

            success = self.run_setup()
            if not success:
                logger.info("Настройка отменена пользователем")
                sys.exit(0)

        # Шаг 2: Монтируем диск
        logger.info("Монтирование Google Drive...")
        mount_success = self.mount()

        if mount_success:
            logger.info(
                "Google Drive смонтирован как %s",
                self.config.drive_path
            )
        else:
            logger.error("Не удалось смонтировать Google Drive")

        # Шаг 3: Обновляем автозапуск
        if self.config.autostart_enabled:
            autostart.update_autostart_command()

        # Шаг 4: Запускаем системный трей (блокирующий вызов)
        logger.info("Запуск системного трея...")
        self.tray.run()

        # После выхода из трея
        logger.info("Приложение завершено")

    def cleanup(self):
        """Очистка при выходе."""
        logger.info("Очистка...")
        self.unmount()
