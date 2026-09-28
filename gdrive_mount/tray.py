"""
Системный трей — иконка в панели задач Windows.
Позволяет управлять монтированием, автозапуском и выходом из приложения.
"""

import logging
import threading
import webbrowser
from io import BytesIO

import pystray
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def create_drive_icon(connected: bool = False) -> Image.Image:
    """
    Создаёт иконку для системного трея.
    Зелёная — подключён, серая — отключён.
    """
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Цвет зависит от состояния подключения
    if connected:
        bg_color = (66, 133, 244, 255)      # Google Blue
        accent_color = (52, 168, 83, 255)    # Google Green
    else:
        bg_color = (128, 128, 128, 255)      # Серый
        accent_color = (96, 96, 96, 255)

    # Рисуем облако (основу)
    draw.rounded_rectangle([4, 14, 60, 50], radius=10, fill=bg_color)
    # Верхушка облака
    draw.ellipse([16, 4, 48, 36], fill=bg_color)
    draw.ellipse([6, 12, 30, 36], fill=bg_color)
    draw.ellipse([34, 8, 58, 32], fill=bg_color)

    # Индикатор состояния (кружок внизу справа)
    draw.ellipse([44, 38, 60, 54], fill=accent_color)

    # Буква "G" на облаке
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except (IOError, OSError):
        font = ImageFont.load_default()

    draw.text((22, 18), "G", fill="white", font=font)

    return img


class TrayApp:
    """
    Приложение в системном трее.
    Управляет иконкой, контекстным меню и взаимодействием с пользователем.
    """

    def __init__(self, app):
        """
        Args:
            app: Экземпляр GDriveMountApp.
        """
        self.app = app
        self.icon: pystray.Icon | None = None
        self._running = False

    def _build_menu(self) -> pystray.Menu:
        """Создаёт контекстное меню трея."""
        mounted = self.app.is_mounted()
        status_text = "✅ Подключён" if mounted else "❌ Отключён"
        drive_text = f"💿 Диск {self.app.config.drive_letter}:"

        return pystray.Menu(
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.MenuItem(drive_text, None, enabled=False),
            pystray.Menu.SEPARATOR,

            # Подключить / Отключить
            pystray.MenuItem(
                "🔌 Отключить" if mounted else "🔗 Подключить",
                self._on_toggle_mount,
            ),

            # Открыть диск в проводнике
            pystray.MenuItem(
                "📂 Открыть в проводнике",
                self._on_open_explorer,
                enabled=mounted,
            ),

            pystray.Menu.SEPARATOR,

            # Автозапуск
            pystray.MenuItem(
                "🚀 Автозапуск с Windows",
                self._on_toggle_autostart,
                checked=lambda item: self.app.is_autostart_enabled(),
            ),

            # Информация о диске
            pystray.MenuItem(
                "ℹ️ Информация о диске",
                self._on_show_info,
            ),

            # Google Drive в браузере
            pystray.MenuItem(
                "🌐 Google Drive в браузере",
                self._on_open_gdrive,
            ),

            # Сменить аккаунт
            pystray.MenuItem(
                "🔄 Сменить аккаунт Google",
                self._on_reconfigure,
            ),

            pystray.Menu.SEPARATOR,

            # Выход
            pystray.MenuItem(
                "❌ Выход",
                self._on_quit,
            ),
        )

    def _update_icon(self):
        """Обновляет иконку и меню."""
        if self.icon:
            mounted = self.app.is_mounted()
            self.icon.icon = create_drive_icon(connected=mounted)
            self.icon.title = (
                f"Google Drive ({self.app.config.drive_letter}:) — "
                + ("Подключён" if mounted else "Отключён")
            )
            self.icon.menu = self._build_menu()

    def on_mount_status_changed(self, mounted: bool):
        """Callback при изменении статуса монтирования."""
        self._update_icon()
        if mounted:
            self._notify("Google Drive подключён",
                         f"Диск {self.app.config.drive_letter}: готов к работе")
        else:
            self._notify("Google Drive отключён",
                         f"Диск {self.app.config.drive_letter}: недоступен")

    def _notify(self, title: str, message: str):
        """Показывает уведомление Windows."""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception as e:
                logger.debug("Не удалось показать уведомление: %s", e)

    # ─── Обработчики событий меню ─────────────────────────────

    def _on_toggle_mount(self, icon, item):
        """Подключить/отключить диск."""
        def do_toggle():
            if self.app.is_mounted():
                self.app.unmount()
            else:
                success = self.app.mount()
                if not success:
                    self._notify(
                        "Ошибка подключения",
                        "Не удалось подключить Google Drive. Проверьте логи."
                    )
            self._update_icon()

        threading.Thread(target=do_toggle, daemon=True).start()

    def _on_open_explorer(self, icon, item):
        """Открыть диск в проводнике Windows."""
        import subprocess
        try:
            subprocess.Popen(
                ["explorer.exe", self.app.config.drive_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as e:
            logger.error("Ошибка открытия проводника: %s", e)

    def _on_toggle_autostart(self, icon, item):
        """Включить/отключить автозапуск."""
        if self.app.is_autostart_enabled():
            self.app.disable_autostart()
            self._notify("Автозапуск", "Автозапуск отключён")
        else:
            self.app.enable_autostart()
            self._notify("Автозапуск", "Автозапуск включён")

    def _on_show_info(self, icon, item):
        """Показать информацию о диске."""
        def show_info():
            info = self.app.get_drive_info()
            if info:
                total = info.get("total", 0)
                used = info.get("used", 0)
                free = info.get("free", 0)

                def fmt(b):
                    if b >= 1_099_511_627_776:
                        return f"{b / 1_099_511_627_776:.1f} ТБ"
                    elif b >= 1_073_741_824:
                        return f"{b / 1_073_741_824:.1f} ГБ"
                    else:
                        return f"{b / 1_048_576:.1f} МБ"

                self._notify(
                    "Google Drive",
                    f"Всего: {fmt(total)}\n"
                    f"Занято: {fmt(used)}\n"
                    f"Свободно: {fmt(free)}"
                )
            else:
                self._notify("Google Drive", "Не удалось получить информацию")

        threading.Thread(target=show_info, daemon=True).start()

    def _on_open_gdrive(self, icon, item):
        """Открыть Google Drive в браузере."""
        webbrowser.open("https://drive.google.com")

    def _on_reconfigure(self, icon, item):
        """Сменить аккаунт Google."""
        def do_reconfigure():
            was_mounted = self.app.is_mounted()
            if was_mounted:
                self.app.unmount()

            self._notify("Настройка", "Откроется окно для входа в Google...")
            success = self.app.reconfigure()

            if success and was_mounted:
                self.app.mount()
            self._update_icon()

        threading.Thread(target=do_reconfigure, daemon=True).start()

    def _on_quit(self, icon, item):
        """Выход из приложения."""
        logger.info("Выход из приложения...")
        self._running = False
        self.app.unmount()
        icon.stop()

    # ─── Запуск ───────────────────────────────────────────────

    def run(self):
        """Запускает приложение в системном трее."""
        self._running = True
        mounted = self.app.is_mounted()

        self.icon = pystray.Icon(
            name="GDriveMount",
            icon=create_drive_icon(connected=mounted),
            title=f"Google Drive ({self.app.config.drive_letter}:)",
            menu=self._build_menu(),
        )

        logger.info("Запуск системного трея...")
        self.icon.run()

    def stop(self):
        """Останавливает трей."""
        self._running = False
        if self.icon:
            self.icon.stop()
