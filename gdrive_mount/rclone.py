"""
Менеджер rclone — скачивание, настройка и монтирование Google Drive.
Использует rclone + WinFsp для создания виртуального диска.
"""

import os
import re
import sys
import time
import shutil
import logging
import zipfile
import subprocess
import threading
import webbrowser
from pathlib import Path
from urllib.request import urlretrieve, Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

RCLONE_DOWNLOAD_URL = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
WINFSP_DOWNLOAD_URL = "https://github.com/winfsp/winfsp/releases/latest"
WINFSP_MSI_PATTERN = "winfsp-"


class RcloneManager:
    """
    Управляет жизненным циклом rclone:
    - Скачивание и установка
    - Настройка Google Drive remote
    - Монтирование/размонтирование
    - Мониторинг состояния
    """

    def __init__(self, config):
        self.config = config
        self._mount_process: subprocess.Popen | None = None
        self._monitor_thread: threading.Thread | None = None
        self._should_run = False
        self._on_status_change = None  # Callback для изменения статуса

    # ─── Установка rclone ─────────────────────────────────────

    def is_rclone_installed(self) -> bool:
        """Проверяет, установлен ли rclone."""
        return self.config.rclone_exe.exists()

    def download_rclone(self, progress_callback=None) -> bool:
        """
        Скачивает и распаковывает rclone.
        
        Args:
            progress_callback: Функция(downloaded, total) для отображения прогресса.
        
        Returns:
            True если успешно, False при ошибке.
        """
        zip_path = self.config.app_dir / "rclone_download.zip"

        try:
            logger.info("Скачиваю rclone с %s", RCLONE_DOWNLOAD_URL)

            if progress_callback:
                self._download_with_progress(
                    RCLONE_DOWNLOAD_URL, zip_path, progress_callback
                )
            else:
                urlretrieve(RCLONE_DOWNLOAD_URL, str(zip_path))

            logger.info("Распаковка rclone...")
            self.config.rclone_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(str(zip_path), 'r') as zf:
                # Ищем rclone.exe в архиве
                for name in zf.namelist():
                    if name.endswith("rclone.exe"):
                        data = zf.read(name)
                        with open(str(self.config.rclone_exe), 'wb') as f:
                            f.write(data)
                        logger.info("rclone извлечён: %s", self.config.rclone_exe)
                        break
                else:
                    logger.error("rclone.exe не найден в архиве")
                    return False

            # Удаляем архив
            zip_path.unlink(missing_ok=True)

            # Проверяем работоспособность
            result = subprocess.run(
                [str(self.config.rclone_exe), "version"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            logger.info("rclone версия: %s", result.stdout.split('\n')[0])
            return True

        except (URLError, IOError, zipfile.BadZipFile) as e:
            logger.error("Ошибка скачивания rclone: %s", e)
            zip_path.unlink(missing_ok=True)
            return False

    @staticmethod
    def _download_with_progress(url: str, dest: Path, callback):
        """Скачивание файла с отображением прогресса."""
        req = Request(url, headers={"User-Agent": "GDriveMount/1.0"})
        response = urlopen(req)
        total = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        block_size = 65536

        with open(str(dest), 'wb') as f:
            while True:
                chunk = response.read(block_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                callback(downloaded, total)

    # ─── Проверка WinFsp ──────────────────────────────────────

    @staticmethod
    def is_winfsp_installed() -> bool:
        """Проверяет, установлен ли WinFsp (необходим для монтирования)."""
        # Проверяем стандартные пути
        program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        program_files_64 = os.environ.get("ProgramFiles", r"C:\Program Files")

        for base in [program_files, program_files_64]:
            winfsp_dir = Path(base) / "WinFsp"
            if winfsp_dir.exists():
                logger.info("WinFsp найден: %s", winfsp_dir)
                return True

        # Проверяем через реестр
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\WinFsp",
                0, winreg.KEY_READ
            )
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            pass

        logger.warning("WinFsp не найден")
        return False

    @staticmethod
    def get_winfsp_download_url() -> str:
        """Возвращает URL для скачивания WinFsp."""
        return "https://winfsp.dev/rel/"

    # ─── Настройка Google Drive ───────────────────────────────

    def is_remote_configured(self) -> bool:
        """Проверяет, настроен ли Google Drive remote в rclone."""
        if not self.is_rclone_installed():
            return False
        if not self.config.rclone_config_path.exists():
            return False

        try:
            result = subprocess.run(
                [
                    str(self.config.rclone_exe),
                    "listremotes",
                    "--config", str(self.config.rclone_config_path)
                ],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10
            )
            remote_name = f"{self.config.remote_name}:"
            configured = remote_name in result.stdout
            logger.info(
                "Remote '%s' %s",
                self.config.remote_name,
                "настроен" if configured else "не настроен"
            )
            return configured
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error("Ошибка проверки remote: %s", e)
            return False

    def configure_remote(self) -> bool:
        """
        Запускает настройку Google Drive remote через rclone.
        Открывает консольное окно для интерактивной авторизации.
        Возвращает True если remote успешно настроен.
        """
        logger.info("Запуск настройки Google Drive remote...")

        try:
            # Используем rclone config create — он автоматически
            # откроет браузер для OAuth авторизации Google
            process = subprocess.Popen(
                [
                    str(self.config.rclone_exe),
                    "config", "create",
                    self.config.remote_name, "drive",
                    "--config", str(self.config.rclone_config_path),
                    "--drive-scope", "drive",
                    "--drive-acknowledge-abuse", "true",
                ],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            # Ждём завершения настройки
            process.wait()

            # Проверяем, что remote создан
            if self.is_remote_configured():
                logger.info("Google Drive remote успешно настроен!")
                return True
            else:
                logger.warning("Remote не найден после настройки")
                return False

        except OSError as e:
            logger.error("Ошибка запуска rclone config: %s", e)
            return False

    def reconfigure_remote(self) -> bool:
        """Пересоздаёт remote (для смены аккаунта Google)."""
        logger.info("Пересоздание Google Drive remote...")
        # Удаляем конфиг-файл
        try:
            if self.config.rclone_config_path.exists():
                self.config.rclone_config_path.unlink()
                logger.info("Конфигурация удалена")
        except OSError:
            pass

        # Пробуем удалить через rclone
        try:
            subprocess.run(
                [
                    str(self.config.rclone_exe),
                    "config", "delete", self.config.remote_name,
                    "--config", str(self.config.rclone_config_path)
                ],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10
            )
        except (subprocess.TimeoutExpired, OSError):
            pass

        return self.authorize_via_browser()

    def authorize_via_browser(self, url_callback=None, status_callback=None) -> bool:
        """
        Запускает OAuth авторизацию Google Drive через собственный сервер.

        НЕ использует rclone authorize — вместо этого запускает свой
        HTTP-сервер для OAuth callback, напрямую обменивает код на токен
        через Google API и записывает конфиг rclone.

        Args:
            url_callback:    callable(url) — получает URL для браузера.
            status_callback: callable(text) — получает текст статуса.

        Returns:
            True если авторизация успешна и конфиг записан.
        """
        from gdrive_mount.oauth import GoogleDriveOAuth

        oauth = GoogleDriveOAuth()
        token_json = oauth.authorize(
            url_callback=url_callback,
            status_callback=status_callback,
        )

        if token_json:
            self._write_rclone_config(token_json)
            return True

        return False

    def _write_rclone_config(self, token: str):
        """
        Записывает конфигурацию rclone с полученным OAuth-токеном.

        Args:
            token: JSON-строка с OAuth-токеном от Google.
        """
        config_content = (
            f"[{self.config.remote_name}]\n"
            f"type = drive\n"
            f"scope = drive\n"
            f"token = {token}\n"
            f"team_drive = \n"
        )

        self.config.rclone_config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(
            str(self.config.rclone_config_path), 'w', encoding='utf-8'
        ) as f:
            f.write(config_content)

        logger.info(
            "Конфигурация rclone записана: %s",
            self.config.rclone_config_path
        )

    # ─── Монтирование ─────────────────────────────────────────

    def mount(self) -> bool:
        """
        Монтирует Google Drive как локальный диск Windows.
        Возвращает True если монтирование запущено успешно.
        """
        if self.is_mounted():
            logger.info("Диск уже смонтирован: %s", self.config.drive_path)
            return True

        if not self.is_rclone_installed():
            logger.error("rclone не установлен")
            return False

        if not self.is_remote_configured():
            logger.error("Google Drive remote не настроен")
            return False

        drive = self.config.get_mount_point()
        remote = f"{self.config.remote_name}:"

        cmd = [
            str(self.config.rclone_exe),
            "mount", remote, drive,
            "--config", str(self.config.rclone_config_path),

            # Режим кеширования — полный (чтение и запись)
            "--vfs-cache-mode", "full",
            "--vfs-cache-max-size", self.config.cache_size,
            "--cache-dir", str(self.config.cache_dir),

            # Оптимизация производительности
            "--dir-cache-time", "30m",
            "--vfs-read-ahead", "128M",
            "--vfs-write-back", "5s",
            "--vfs-cache-max-age", "24h",
            "--buffer-size", "64M",
            "--transfers", "8",

            # Имя тома в проводнике
            "--volname", "Google Drive",

            # Логирование
            "--log-file", str(self.config.log_file),
            "--log-level", "INFO",

            # Права доступа (полный доступ)
            "--file-perms", "0777",
            "--dir-perms", "0777",
        ]

        try:
            logger.info("Монтирование %s -> %s", remote, drive)
            logger.info("Команда: %s", " ".join(cmd))

            self._mount_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            # Запускаем мониторинг
            self._should_run = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_mount, daemon=True
            )
            self._monitor_thread.start()

            # Ждём появления диска (до 20 секунд)
            for i in range(40):
                time.sleep(0.5)

                # Проверяем, не упал ли процесс
                if self._mount_process.poll() is not None:
                    stderr_output = ""
                    try:
                        stderr_output = self._mount_process.stderr.read().decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        pass
                    logger.error(
                        "rclone mount завершился с кодом %d. Stderr: %s",
                        self._mount_process.returncode,
                        stderr_output[:500]
                    )
                    self._mount_process = None
                    return False

                if self.is_mounted():
                    logger.info("Диск успешно смонтирован: %s", drive)
                    if self._on_status_change:
                        self._on_status_change(True)
                    return True

            logger.warning("Диск не появился за 20 секунд, но процесс работает")
            return True

        except OSError as e:
            logger.error("Ошибка запуска rclone mount: %s", e)
            return False

    def unmount(self) -> bool:
        """Размонтирует диск."""
        logger.info("Размонтирование диска...")
        self._should_run = False

        # Останавливаем наш процесс
        if self._mount_process:
            try:
                self._mount_process.terminate()
                try:
                    self._mount_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._mount_process.kill()
                    self._mount_process.wait(timeout=5)
                logger.info("Процесс rclone mount остановлен")
            except OSError as e:
                logger.error("Ошибка остановки rclone: %s", e)
            finally:
                self._mount_process = None

        # Убиваем все оставшиеся процессы rclone (на случай зависания)
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "rclone.exe"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass

        if self._on_status_change:
            self._on_status_change(False)

        return True

    def is_mounted(self) -> bool:
        """Проверяет, смонтирован ли диск."""
        try:
            return os.path.isdir(self.config.drive_path)
        except OSError:
            return False

    def _monitor_mount(self):
        """Фоновый мониторинг состояния монтирования."""
        was_mounted = False
        while self._should_run:
            time.sleep(5)
            currently_mounted = self.is_mounted()

            if was_mounted and not currently_mounted:
                logger.warning("Диск отключился! Попытка перемонтирования...")
                if self._mount_process and self._mount_process.poll() is not None:
                    # Процесс rclone упал — перезапускаем
                    self._mount_process = None
                    time.sleep(2)
                    self.mount()

            was_mounted = currently_mounted

    def set_status_callback(self, callback):
        """Устанавливает callback для изменения статуса монтирования."""
        self._on_status_change = callback

    # ─── Информация ───────────────────────────────────────────

    def get_drive_info(self) -> dict | None:
        """Получает информацию о Google Drive (свободное/занятое место)."""
        if not self.is_rclone_installed() or not self.is_remote_configured():
            return None

        try:
            result = subprocess.run(
                [
                    str(self.config.rclone_exe),
                    "about", f"{self.config.remote_name}:",
                    "--config", str(self.config.rclone_config_path),
                    "--json",
                ],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=30
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, OSError, ValueError) as e:
            logger.error("Ошибка получения информации о диске: %s", e)

        return None

    def get_rclone_version(self) -> str:
        """Возвращает версию rclone."""
        if not self.is_rclone_installed():
            return "не установлен"
        try:
            result = subprocess.run(
                [str(self.config.rclone_exe), "version"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5
            )
            return result.stdout.strip().split('\n')[0]
        except (subprocess.TimeoutExpired, OSError):
            return "ошибка определения версии"
