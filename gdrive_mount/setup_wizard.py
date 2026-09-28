"""
Мастер первоначальной настройки (Setup Wizard).
GUI на tkinter для первого запуска: проверка зависимостей,
скачивание rclone, авторизация Google Drive.
"""

import os
import sys
import threading
import webbrowser
import logging
import tkinter as tk
from tkinter import ttk, messagebox

logger = logging.getLogger(__name__)


class SetupWizard:
    """
    Пошаговый мастер настройки GDriveMount.
    
    Этапы:
    1. Приветствие и проверка WinFsp
    2. Скачивание rclone
    3. Выбор буквы диска
    4. Авторизация Google Drive
    5. Завершение
    """

    def __init__(self, app):
        self.app = app
        self.root: tk.Tk | None = None
        self.current_step = 0
        self.result = False  # True если настройка завершена успешно
        self._drive_letter_var = None

    def run(self) -> bool:
        """
        Запускает мастер настройки.
        Возвращает True если настройка завершена успешно.
        """
        self.root = tk.Tk()
        self.root.title("GDrive Mount — Настройка")
        self.root.geometry("550x420")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Центрируем окно
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 550) // 2
        y = (self.root.winfo_screenheight() - 420) // 2
        self.root.geometry(f"+{x}+{y}")

        # Стиль
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("Step.TLabel", font=("Segoe UI", 9), foreground="gray")
        style.configure("Big.TButton", font=("Segoe UI", 11), padding=10)

        self._show_step_welcome()
        self.root.mainloop()
        return self.result

    def _clear_frame(self):
        """Очищает содержимое окна."""
        for widget in self.root.winfo_children():
            widget.destroy()

    def _add_header(self, title: str, subtitle: str = "", step: int = 0, total: int = 4):
        """Добавляет заголовок и подзаголовок."""
        header_frame = ttk.Frame(self.root, padding=20)
        header_frame.pack(fill=tk.X)

        ttk.Label(header_frame, text=title, style="Title.TLabel").pack(anchor=tk.W)

        if subtitle:
            ttk.Label(
                header_frame, text=subtitle, style="Subtitle.TLabel",
                wraplength=490
            ).pack(anchor=tk.W, pady=(5, 0))

        if step > 0:
            ttk.Label(
                header_frame, text=f"Шаг {step} из {total}",
                style="Step.TLabel"
            ).pack(anchor=tk.W, pady=(5, 0))

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)

    # ─── Шаг 1: Приветствие ───────────────────────────────────

    def _show_step_welcome(self):
        """Шаг 1: Приветствие и проверка WinFsp."""
        self._clear_frame()
        self._add_header(
            "🚀 Добро пожаловать в GDrive Mount!",
            "Эта программа подключит ваш Google Drive как локальный диск "
            "Windows (до 5 ТБ). Файлы будут доступны прямо в Проводнике.",
            step=1
        )

        content = ttk.Frame(self.root, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        # Проверяем WinFsp
        winfsp_ok = self.app.rclone.is_winfsp_installed()

        if winfsp_ok:
            ttk.Label(
                content,
                text="✅ WinFsp установлен — всё готово для продолжения!",
                font=("Segoe UI", 10),
                foreground="green"
            ).pack(anchor=tk.W, pady=5)
        else:
            ttk.Label(
                content,
                text="⚠️ Необходимо установить WinFsp (драйвер виртуальных дисков)",
                font=("Segoe UI", 10),
                foreground="red"
            ).pack(anchor=tk.W, pady=5)

            ttk.Label(
                content,
                text="WinFsp — бесплатный драйвер, который позволяет создавать\n"
                     "виртуальные диски в Windows. Без него монтирование невозможно.",
                wraplength=490
            ).pack(anchor=tk.W, pady=5)

            def open_winfsp():
                webbrowser.open("https://winfsp.dev/rel/")

            ttk.Button(
                content, text="📥 Скачать WinFsp",
                command=open_winfsp
            ).pack(anchor=tk.W, pady=5)

            ttk.Label(
                content,
                text="После установки WinFsp нажмите «Проверить снова»",
                font=("Segoe UI", 9), foreground="gray"
            ).pack(anchor=tk.W, pady=(10, 0))

        # Кнопки
        btn_frame = ttk.Frame(self.root, padding=20)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        if winfsp_ok:
            ttk.Button(
                btn_frame, text="Далее →",
                command=self._show_step_rclone, style="Big.TButton"
            ).pack(side=tk.RIGHT)
        else:
            ttk.Button(
                btn_frame, text="🔄 Проверить снова",
                command=self._show_step_welcome
            ).pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame, text="Отмена",
            command=self._on_close
        ).pack(side=tk.LEFT)

    # ─── Шаг 2: Скачивание rclone ─────────────────────────────

    def _show_step_rclone(self):
        """Шаг 2: Скачивание rclone."""
        self._clear_frame()
        self._add_header(
            "📦 Установка компонентов",
            "Скачиваю rclone — движок для работы с Google Drive...",
            step=2
        )

        content = ttk.Frame(self.root, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        if self.app.rclone.is_rclone_installed():
            version = self.app.rclone.get_rclone_version()
            ttk.Label(
                content,
                text=f"✅ rclone уже установлен: {version}",
                font=("Segoe UI", 10), foreground="green"
            ).pack(anchor=tk.W, pady=10)

            btn_frame = ttk.Frame(self.root, padding=20)
            btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
            ttk.Button(
                btn_frame, text="Далее →",
                command=self._show_step_drive_letter, style="Big.TButton"
            ).pack(side=tk.RIGHT)
            ttk.Button(
                btn_frame, text="← Назад",
                command=self._show_step_welcome
            ).pack(side=tk.LEFT)
            return

        # Прогресс-бар
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(
            content, variable=progress_var,
            maximum=100, length=480
        )
        progress_bar.pack(pady=10)

        status_label = ttk.Label(content, text="Скачивание...")
        status_label.pack(pady=5)

        def download():
            def on_progress(downloaded, total):
                if total > 0:
                    pct = (downloaded / total) * 100
                    progress_var.set(pct)
                    mb = downloaded / 1_048_576
                    total_mb = total / 1_048_576
                    self.root.after(0, lambda: status_label.configure(
                        text=f"Скачано: {mb:.1f} / {total_mb:.1f} МБ ({pct:.0f}%)"
                    ))

            success = self.app.rclone.download_rclone(progress_callback=on_progress)

            if success:
                self.root.after(0, lambda: status_label.configure(
                    text="✅ rclone успешно установлен!"
                ))
                self.root.after(1000, self._show_step_drive_letter)
            else:
                self.root.after(0, lambda: status_label.configure(
                    text="❌ Ошибка скачивания. Проверьте интернет-соединение."
                ))
                self.root.after(0, lambda: _add_retry_button())

        def _add_retry_button():
            ttk.Button(
                content, text="🔄 Попробовать снова",
                command=self._show_step_rclone
            ).pack(pady=10)

        threading.Thread(target=download, daemon=True).start()

    # ─── Шаг 3: Выбор буквы диска ────────────────────────────

    def _show_step_drive_letter(self):
        """Шаг 3: Выбор буквы диска."""
        self._clear_frame()
        self._add_header(
            "💿 Настройка диска",
            "Выберите букву для вашего Google Drive диска.",
            step=3
        )

        content = ttk.Frame(self.root, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        # Находим свободные буквы дисков
        used_letters = set()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if os.path.exists(f"{letter}:\\"):
                used_letters.add(letter)

        free_letters = [
            l for l in "GHIJKLMNOPQRSTUVWXYZ"
            if l not in used_letters
        ]

        if not free_letters:
            free_letters = ["G"]  # Fallback

        ttk.Label(
            content, text="Буква диска:",
            font=("Segoe UI", 11)
        ).pack(anchor=tk.W, pady=(0, 5))

        self._drive_letter_var = tk.StringVar(
            value=self.app.config.drive_letter
            if self.app.config.drive_letter in free_letters
            else free_letters[0]
        )

        letter_frame = ttk.Frame(content)
        letter_frame.pack(anchor=tk.W, pady=5)

        combo = ttk.Combobox(
            letter_frame, textvariable=self._drive_letter_var,
            values=[f"{l}:" for l in free_letters],
            state="readonly", width=5, font=("Segoe UI", 14)
        )
        combo.pack(side=tk.LEFT)

        ttk.Label(
            letter_frame, text="  ← Этот диск появится в Проводнике",
            font=("Segoe UI", 9), foreground="gray"
        ).pack(side=tk.LEFT)

        # Автозапуск
        autostart_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            content,
            text="🚀 Запускать автоматически при входе в Windows",
            variable=autostart_var
        ).pack(anchor=tk.W, pady=(20, 5))

        ttk.Label(
            content,
            text="Программа будет работать скрыто в системном трее.\n"
                 "Диск будет автоматически подключаться при каждом запуске.",
            wraplength=490, font=("Segoe UI", 9), foreground="gray"
        ).pack(anchor=tk.W, pady=5)

        # Кнопки
        btn_frame = ttk.Frame(self.root, padding=20)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        def on_next():
            letter = self._drive_letter_var.get().strip(":")
            self.app.config.drive_letter = letter
            self.app.config.autostart_enabled = autostart_var.get()
            if autostart_var.get():
                self.app.enable_autostart()
            self._show_step_auth()

        ttk.Button(
            btn_frame, text="Далее →",
            command=on_next, style="Big.TButton"
        ).pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame, text="← Назад",
            command=self._show_step_rclone
        ).pack(side=tk.LEFT)

    # ─── Шаг 4: Авторизация Google ────────────────────────────

    def _show_step_auth(self):
        """Шаг 4: Авторизация Google Drive через браузер."""
        self._clear_frame()
        self._add_header(
            "🔑 Вход в Google",
            "Авторизуйтесь через браузер для подключения Google Drive.\n"
            "Войдите в аккаунт с подпиской Google One (5 ТБ).",
            step=4
        )

        content = ttk.Frame(self.root, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        # Описание процесса
        ttk.Label(
            content,
            text="📌 Что произойдёт:",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor=tk.W, pady=(0, 5))

        ttk.Label(
            content,
            text="1. Автоматически откроется браузер со страницей входа Google\n"
                 "2. Войдите в аккаунт и разрешите доступ к Google Drive\n"
                 "3. После входа авторизация завершится автоматически",
            wraplength=490, font=("Segoe UI", 10)
        ).pack(anchor=tk.W, pady=(0, 10))

        # Статус авторизации
        status_label = ttk.Label(
            content, text="Нажмите кнопку для начала авторизации.",
            font=("Segoe UI", 10), wraplength=490
        )
        status_label.pack(anchor=tk.W, pady=(0, 5))

        # Фрейм для отображения URL (скрыт изначально)
        url_frame = ttk.LabelFrame(content, text="🔗 Ссылка для авторизации", padding=10)

        url_var = tk.StringVar()
        url_entry = ttk.Entry(
            url_frame, textvariable=url_var, state="readonly",
            font=("Consolas", 9), width=60
        )

        url_buttons_frame = ttk.Frame(url_frame)

        def _show_url_in_gui(url):
            """Показывает URL авторизации в окне мастера."""
            url_var.set(url)
            url_frame.pack(anchor=tk.W, pady=10, fill=tk.X)
            url_entry.pack(fill=tk.X, pady=(0, 5))
            url_buttons_frame.pack(anchor=tk.W)

            ttk.Button(
                url_buttons_frame, text="🌐 Открыть в браузере",
                command=lambda: webbrowser.open(url)
            ).pack(side=tk.LEFT, padx=(0, 5))

            ttk.Button(
                url_buttons_frame, text="📋 Скопировать ссылку",
                command=lambda: _copy_url(url)
            ).pack(side=tk.LEFT)

        def _copy_url(url):
            """Копирует URL в буфер обмена."""
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            # Краткое уведомление
            status_label.configure(
                text="📋 Ссылка скопирована! Вставьте в браузер.",
                foreground="blue"
            )

        def _on_url_callback(url):
            """Callback из rclone — URL получен."""
            self.root.after(0, lambda: _show_url_in_gui(url))

        def _on_status_callback(text):
            """Callback из rclone — обновление статуса."""
            self.root.after(0, lambda: status_label.configure(
                text=text,
                foreground="blue"
            ))

        # ─── Кнопки внизу ────────────────────────────────────

        btn_frame = ttk.Frame(self.root, padding=20)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        def start_browser_auth():
            """Основной способ: авторизация через браузер."""
            auth_btn.configure(state="disabled")
            fallback_btn.configure(state="disabled")
            status_label.configure(
                text="⏳ Запуск авторизации... Ожидайте открытия браузера.",
                foreground="blue"
            )

            def do_auth():
                success = self.app.rclone.authorize_via_browser(
                    url_callback=_on_url_callback,
                    status_callback=_on_status_callback,
                )

                if success:
                    self.root.after(0, lambda: status_label.configure(
                        text="✅ Авторизация успешна! Google Drive подключён.",
                        foreground="green"
                    ))
                    self.root.after(1500, self._show_step_done)
                else:
                    self.root.after(0, lambda: status_label.configure(
                        text="❌ Не удалось авторизоваться. Попробуйте снова\n"
                             "или используйте альтернативный способ (кнопка ниже).",
                        foreground="red"
                    ))
                    self.root.after(0, lambda: auth_btn.configure(state="normal"))
                    self.root.after(0, lambda: fallback_btn.configure(state="normal"))

            threading.Thread(target=do_auth, daemon=True).start()

        def start_console_auth():
            """Fallback: авторизация через консольное окно rclone."""
            auth_btn.configure(state="disabled")
            fallback_btn.configure(state="disabled")
            status_label.configure(
                text="⏳ Открывается консольное окно rclone...\n"
                     "Следуйте инструкциям в консоли.",
                foreground="blue"
            )

            def do_console_auth():
                success = self.app.rclone.configure_remote()
                if success:
                    self.root.after(0, lambda: status_label.configure(
                        text="✅ Авторизация успешна!",
                        foreground="green"
                    ))
                    self.root.after(1500, self._show_step_done)
                else:
                    self.root.after(0, lambda: status_label.configure(
                        text="❌ Ошибка. Попробуйте снова.",
                        foreground="red"
                    ))
                    self.root.after(0, lambda: auth_btn.configure(state="normal"))
                    self.root.after(0, lambda: fallback_btn.configure(state="normal"))

            threading.Thread(target=do_console_auth, daemon=True).start()

        # Основная кнопка
        auth_btn = ttk.Button(
            btn_frame, text="🔐 Войти через браузер",
            command=start_browser_auth, style="Big.TButton"
        )
        auth_btn.pack(side=tk.RIGHT, padx=(5, 0))

        # Fallback кнопка
        fallback_btn = ttk.Button(
            btn_frame, text="🔧 Альтернативный (консоль)",
            command=start_console_auth,
        )
        fallback_btn.pack(side=tk.RIGHT, padx=(5, 0))

        # Назад
        ttk.Button(
            btn_frame, text="← Назад",
            command=self._show_step_drive_letter
        ).pack(side=tk.LEFT)

    # ─── Шаг 5: Завершение ────────────────────────────────────

    def _show_step_done(self):
        """Шаг 5: Настройка завершена."""
        self._clear_frame()
        self._add_header(
            "🎉 Настройка завершена!",
            f"Google Drive будет доступен как диск {self.app.config.drive_letter}:"
        )

        content = ttk.Frame(self.root, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            content,
            text="✅ WinFsp установлен\n"
                 "✅ Rclone установлен\n"
                 "✅ Google Drive авторизован\n"
                 f"✅ Диск: {self.app.config.drive_letter}:\n"
                 f"✅ Автозапуск: {'включён' if self.app.config.autostart_enabled else 'отключён'}",
            font=("Segoe UI", 11),
            foreground="green"
        ).pack(anchor=tk.W, pady=10)

        ttk.Label(
            content,
            text="Программа свернётся в системный трей (🔽 в панели задач).\n"
                 "Правый клик на иконке — управление диском.",
            wraplength=490, font=("Segoe UI", 10)
        ).pack(anchor=tk.W, pady=10)

        # Кнопка завершения
        btn_frame = ttk.Frame(self.root, padding=20)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        def finish():
            self.app.config.configured = True
            self.result = True
            self.root.destroy()

        ttk.Button(
            btn_frame, text="✨ Запустить Google Drive!",
            command=finish, style="Big.TButton"
        ).pack(side=tk.RIGHT)

    def _on_close(self):
        """Закрытие без завершения настройки."""
        if messagebox.askyesno(
            "Отмена настройки",
            "Вы уверены? Без настройки программа не сможет подключить Google Drive."
        ):
            self.result = False
            self.root.destroy()
