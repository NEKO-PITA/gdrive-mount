r"""
Управление конфигурацией приложения.
Хранит настройки в JSON-файле в %LOCALAPPDATA%\GDriveMount.
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """Конфигурация приложения GDriveMount."""

    # Значения по умолчанию
    DEFAULT_DRIVE_LETTER = "G"
    DEFAULT_CACHE_SIZE = "10G"
    DEFAULT_REMOTE_NAME = "gdrive"
    DEFAULT_CACHE_TIME = "30m"
    DEFAULT_READ_AHEAD = "128M"
    DEFAULT_WRITE_BACK = "5s"
    DEFAULT_LOG_LEVEL = "INFO"

    def __init__(self):
        self.app_dir = self._get_app_dir()
        self.config_file = self.app_dir / "config.json"
        self.rclone_dir = self.app_dir / "rclone"
        self.cache_dir = self.app_dir / "vfs-cache"
        self.log_dir = self.app_dir / "logs"
        self._data = self._load()

        # Создаём необходимые директории
        for d in [self.app_dir, self.rclone_dir, self.cache_dir, self.log_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_app_dir() -> Path:
        """Возвращает путь к директории приложения."""
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "GDriveMount"
        return Path.home() / ".gdrive_mount"

    def _load(self) -> dict:
        """Загружает конфигурацию из файла."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("Конфигурация загружена: %s", self.config_file)
                return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Ошибка загрузки конфигурации: %s", e)
        return {}

    def save(self):
        """Сохраняет конфигурацию в файл."""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            logger.info("Конфигурация сохранена: %s", self.config_file)
        except IOError as e:
            logger.error("Ошибка сохранения конфигурации: %s", e)

    # ─── Свойства ─────────────────────────────────────────────

    @property
    def drive_letter(self) -> str:
        return self._data.get("drive_letter", self.DEFAULT_DRIVE_LETTER)

    @drive_letter.setter
    def drive_letter(self, value: str):
        self._data["drive_letter"] = value.upper().strip(":")
        self.save()

    @property
    def cache_size(self) -> str:
        return self._data.get("cache_size", self.DEFAULT_CACHE_SIZE)

    @cache_size.setter
    def cache_size(self, value: str):
        self._data["cache_size"] = value
        self.save()

    @property
    def remote_name(self) -> str:
        return self._data.get("remote_name", self.DEFAULT_REMOTE_NAME)

    @property
    def autostart_enabled(self) -> bool:
        return self._data.get("autostart", True)

    @autostart_enabled.setter
    def autostart_enabled(self, value: bool):
        self._data["autostart"] = value
        self.save()

    @property
    def configured(self) -> bool:
        return self._data.get("configured", False)

    @configured.setter
    def configured(self, value: bool):
        self._data["configured"] = value
        self.save()

    @property
    def minimize_on_start(self) -> bool:
        """Сворачивать в трей при запуске Windows."""
        return self._data.get("minimize_on_start", True)

    @minimize_on_start.setter
    def minimize_on_start(self, value: bool):
        self._data["minimize_on_start"] = value
        self.save()

    # ─── Пути ─────────────────────────────────────────────────

    @property
    def rclone_exe(self) -> Path:
        return self.rclone_dir / "rclone.exe"

    @property
    def rclone_config_path(self) -> Path:
        return self.app_dir / "rclone.conf"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "rclone_mount.log"

    @property
    def app_log_file(self) -> Path:
        return self.log_dir / "app.log"

    @property
    def drive_path(self) -> str:
        """Полный путь к смонтированному диску, например 'G:\\'."""
        return f"{self.drive_letter}:\\"

    def get_mount_point(self) -> str:
        """Возвращает точку монтирования: 'G:'."""
        return f"{self.drive_letter}:"

    def __repr__(self):
        return (
            f"Config(drive={self.drive_letter}:, "
            f"configured={self.configured}, "
            f"autostart={self.autostart_enabled})"
        )
