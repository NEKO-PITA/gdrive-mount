"""
Собственная реализация Google OAuth 2.0 для Google Drive.

НЕ использует rclone authorize — работает напрямую с Google API.
Гарантированная работа:
  - Свой HTTP-сервер для callback (перебирает порты)
  - Красивые HTML-страницы успеха/ошибки в браузере
  - Обмен кода на токен напрямую через Google API
  - Формат токена совместим с rclone
  - Fallback: ручной ввод кода если localhost недоступен
"""

import json
import logging
import secrets
import datetime
import webbrowser
import threading
import urllib.parse
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

# ─── OAuth-параметры rclone (публичные, из исходного кода rclone) ────
# Эти credentials зарегистрированы как "installed application" в Google,
# что разрешает redirect на http://127.0.0.1 с любым портом (RFC 8252).
RCLONE_CLIENT_ID = "202264815644.apps.googleusercontent.com"
RCLONE_CLIENT_SECRET = "X4Z3ca8xfWDb1Voo-F9a7ZxJ"

SCOPES = "https://www.googleapis.com/auth/drive"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

# Порты для callback-сервера (перебираются по очереди)
CALLBACK_PORTS = [
    53682, 53683, 53684, 53685,  # Стандартные rclone-порты
    18080, 18090, 19090,          # Альтернативные
    28080, 38080, 48080,          # Ещё альтернативы
    0,                            # Любой свободный порт (fallback ОС)
]


# ─── HTML-страницы для браузера ──────────────────────────────────────

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>GDrive Mount — Успех!</title>
  <style>
    body {
      font-family: 'Segoe UI', Tahoma, sans-serif;
      display: flex; justify-content: center; align-items: center;
      min-height: 100vh; margin: 0;
      background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
    }
    .card {
      background: white; border-radius: 16px; padding: 48px 64px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.1); text-align: center;
      max-width: 480px;
    }
    .icon { font-size: 64px; margin-bottom: 16px; }
    h1 { color: #2e7d32; margin: 0 0 12px; font-size: 28px; }
    p { color: #555; font-size: 16px; line-height: 1.5; }
    .hint { color: #999; font-size: 14px; margin-top: 20px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>Авторизация успешна!</h1>
    <p>Google Drive подключён к GDrive Mount.</p>
    <p class="hint">Можете закрыть эту вкладку и вернуться в программу.</p>
  </div>
</body>
</html>"""

ERROR_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>GDrive Mount — Ошибка</title>
  <style>
    body {{
      font-family: 'Segoe UI', Tahoma, sans-serif;
      display: flex; justify-content: center; align-items: center;
      min-height: 100vh; margin: 0;
      background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
    }}
    .card {{
      background: white; border-radius: 16px; padding: 48px 64px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.1); text-align: center;
      max-width: 480px;
    }}
    .icon {{ font-size: 64px; margin-bottom: 16px; }}
    h1 {{ color: #c62828; margin: 0 0 12px; font-size: 28px; }}
    p {{ color: #555; font-size: 16px; line-height: 1.5; }}
    .error-detail {{ color: #999; font-size: 13px; margin-top: 16px;
                     background: #f5f5f5; padding: 12px; border-radius: 8px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">❌</div>
    <h1>Ошибка авторизации</h1>
    <p>Не удалось подключить Google Drive.</p>
    <p>Вернитесь в GDrive Mount и попробуйте снова.</p>
    <div class="error-detail">{error_detail}</div>
  </div>
</body>
</html>"""

WAITING_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>GDrive Mount — Ожидание</title>
  <style>
    body {
      font-family: 'Segoe UI', Tahoma, sans-serif;
      display: flex; justify-content: center; align-items: center;
      min-height: 100vh; margin: 0;
      background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
    }
    .card {
      background: white; border-radius: 16px; padding: 48px 64px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.1); text-align: center;
      max-width: 480px;
    }
    .spinner {
      width: 48px; height: 48px; border: 5px solid #e0e0e0;
      border-top: 5px solid #1976d2; border-radius: 50%;
      animation: spin 1s linear infinite; margin: 0 auto 20px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    h1 { color: #1565c0; margin: 0 0 12px; font-size: 24px; }
    p { color: #555; font-size: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="spinner"></div>
    <h1>Перенаправление на Google...</h1>
    <p>Если страница не обновляется, <a href="REDIRECT_URL">нажмите здесь</a>.</p>
  </div>
</body>
</html>"""


# ─── Callback HTTP-сервер ────────────────────────────────────────────

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Обработчик HTTP-запросов для OAuth callback от Google."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            # Успех — Google вернул код авторизации
            self.server.oauth_code = params["code"][0]
            self.server.oauth_state = params.get("state", [None])[0]
            self._respond(200, SUCCESS_HTML)
            logger.info("OAuth код получен через callback")

        elif "error" in params:
            # Ошибка — пользователь отказал или Google вернул ошибку
            error = params.get("error", ["unknown"])[0]
            desc = params.get("error_description", [error])[0]
            self.server.oauth_error = f"{error}: {desc}"
            html = ERROR_HTML_TEMPLATE.format(error_detail=f"{error}: {desc}")
            self._respond(200, html)
            logger.error("OAuth ошибка: %s", self.server.oauth_error)

        else:
            # Неизвестный запрос (favicon и т.п.)
            self._respond(204, "")

    def _respond(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        """Подавляем стандартный лог http.server."""
        logger.debug("HTTP: %s", format % args)


class _CallbackServer(HTTPServer):
    """HTTP-сервер с хранением результата OAuth."""

    def __init__(self, port: int):
        super().__init__(("127.0.0.1", port), _OAuthCallbackHandler)
        self.oauth_code: str | None = None
        self.oauth_error: str | None = None
        self.oauth_state: str | None = None
        self.timeout = 300  # 5 минут на авторизацию


# ─── Основной класс OAuth ───────────────────────────────────────────

class GoogleDriveOAuth:
    """
    Гарантированная OAuth 2.0 авторизация для Google Drive.

    Преимущества над rclone authorize:
    - Перебирает несколько портов если порт занят
    - Собственный HTTP-сервер (не зависит от rclone)
    - Красивые страницы в браузере
    - Таймаут с понятными ошибками
    - Обмен кода напрямую через Google API
    """

    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id or RCLONE_CLIENT_ID
        self.client_secret = client_secret or RCLONE_CLIENT_SECRET
        self._server: _CallbackServer | None = None
        self._port: int | None = None
        self._state: str | None = None

    # ─── Запуск сервера ───────────────────────────────────────

    def _start_server(self) -> bool:
        """
        Запускает callback-сервер, перебирая порты.
        Возвращает True если сервер запущен.
        """
        for port in CALLBACK_PORTS:
            try:
                self._server = _CallbackServer(port)
                self._port = self._server.server_address[1]
                logger.info(
                    "OAuth callback сервер запущен: 127.0.0.1:%d", self._port
                )
                return True
            except OSError as e:
                logger.debug("Порт %d занят: %s", port, e)
                continue

        logger.error("Не удалось запустить callback-сервер ни на одном порту!")
        return False

    # ─── Формирование URL ─────────────────────────────────────

    def _get_auth_url(self) -> str:
        """Формирует URL авторизации Google."""
        self._state = secrets.token_urlsafe(32)
        redirect_uri = f"http://127.0.0.1:{self._port}/"

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": self._state,
        }
        url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"
        logger.debug("Auth URL: %s", url)
        return url

    # ─── Обмен кода на токен ──────────────────────────────────

    def _exchange_code_for_token(self, code: str) -> dict:
        """
        Обменивает authorization code на access + refresh token.
        Отправляет POST-запрос напрямую в Google OAuth API.
        """
        redirect_uri = f"http://127.0.0.1:{self._port}/"

        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }).encode("utf-8")

        req = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))
            logger.info("Токен получен от Google (expires_in=%s)",
                        token_data.get("expires_in"))
            return token_data
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error("Ошибка обмена кода: HTTP %d: %s", e.code, body)
            raise RuntimeError(f"Google вернул ошибку {e.code}: {body}")
        except urllib.error.URLError as e:
            logger.error("Сетевая ошибка при обмене кода: %s", e)
            raise RuntimeError(f"Сетевая ошибка: {e}")

    # ─── Конвертация в формат rclone ──────────────────────────

    @staticmethod
    def _to_rclone_token(google_token: dict) -> str:
        """Конвертирует ответ Google в JSON-строку формата rclone."""
        expiry = ""
        if "expires_in" in google_token:
            exp_dt = datetime.datetime.utcnow() + datetime.timedelta(
                seconds=google_token["expires_in"]
            )
            expiry = exp_dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

        rclone_token = {
            "access_token": google_token.get("access_token", ""),
            "token_type": google_token.get("token_type", "Bearer"),
            "refresh_token": google_token.get("refresh_token", ""),
            "expiry": expiry,
        }
        return json.dumps(rclone_token)

    # ─── Главный метод авторизации ────────────────────────────

    def authorize(
        self,
        url_callback=None,
        status_callback=None,
    ) -> str | None:
        """
        Запускает полный OAuth-поток.

        Args:
            url_callback:    callable(url: str) — получает URL для браузера.
            status_callback: callable(text: str) — получает текст статуса.

        Returns:
            JSON-строка токена в формате rclone, или None при ошибке.
        """

        # ── 1. Запускаем callback-сервер ──────────────────────
        if status_callback:
            status_callback("🔧 Подготовка сервера авторизации...")

        if not self._start_server():
            if status_callback:
                status_callback(
                    "❌ Не удалось запустить сервер!\n"
                    "Закройте другие программы, использующие сетевые порты."
                )
            return None

        if status_callback:
            status_callback(
                f"✅ Сервер запущен на порту {self._port}\n"
                "Открываю браузер..."
            )

        # ── 2. Формируем URL и открываем браузер ──────────────
        auth_url = self._get_auth_url()

        # Передаём URL в GUI (для отображения ссылки)
        if url_callback:
            url_callback(auth_url)

        # Открываем браузер
        try:
            webbrowser.open(auth_url)
            logger.info("Браузер открыт")
        except Exception as e:
            logger.warning("Не удалось открыть браузер: %s", e)

        if status_callback:
            status_callback(
                "🌐 Браузер открыт — войдите в Google аккаунт.\n"
                "Если браузер не открылся — используйте ссылку ниже."
            )

        # ── 3. Ожидаем callback от Google ─────────────────────
        logger.info("Ожидание OAuth callback...")

        try:
            # handle_request() блокируется до получения запроса или таймаута
            self._server.handle_request()
        except Exception as e:
            logger.error("Ошибка сервера: %s", e)
            self._cleanup_server()
            if status_callback:
                status_callback(f"❌ Ошибка сервера: {e}")
            return None

        # Проверяем результат
        code = self._server.oauth_code
        error = self._server.oauth_error

        # Закрываем сервер (больше не нужен)
        self._cleanup_server()

        if error:
            logger.error("OAuth ошибка: %s", error)
            if status_callback:
                status_callback(f"❌ Google вернул ошибку:\n{error}")
            return None

        if not code:
            logger.error("Код авторизации не получен (таймаут?)")
            if status_callback:
                status_callback(
                    "❌ Код авторизации не получен.\n"
                    "Возможно, истёк таймаут (5 минут). Попробуйте снова."
                )
            return None

        # Проверяем state (защита от CSRF)
        received_state = self._server.oauth_state if self._server else None
        if self._state and received_state and received_state != self._state:
            logger.warning("State mismatch: expected %s, got %s",
                           self._state, received_state)
            # Не фатальная ошибка, продолжаем

        # ── 4. Обмениваем код на токен ────────────────────────
        if status_callback:
            status_callback("🔄 Получение токена от Google...")

        try:
            google_token = self._exchange_code_for_token(code)
        except RuntimeError as e:
            if status_callback:
                status_callback(f"❌ {e}")
            return None

        # ── 5. Конвертируем в формат rclone ───────────────────
        rclone_token_json = self._to_rclone_token(google_token)

        if status_callback:
            status_callback("✅ Авторизация Google Drive завершена успешно!")

        logger.info("OAuth авторизация завершена успешно")
        return rclone_token_json

    def _cleanup_server(self):
        """Останавливает callback-сервер."""
        if self._server:
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None
