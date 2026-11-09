"""Telegram notifications with local, untracked credential configuration."""
import json
import os
import time
from pathlib import Path
import requests

class Notifier:
    def __init__(self, token=None, chat_id=None, session=None, timeout=15, config_path=None):
        self._token_override = token
        self._chat_override = chat_id
        self.session = session or requests.Session()
        self.timeout = timeout
        self.config_path = Path(config_path or "config/telegram.json")
        self.last_error = None
        self.last_success_at = None

    def _credentials(self):
        token = self._token_override or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = self._chat_override or os.environ.get("TELEGRAM_CHAT_ID", "")
        if not (token and chat_id):
            try:
                config = json.loads(self.config_path.read_text())
                token = token or str(config.get("bot_token", "")).strip()
                chat_id = chat_id or str(config.get("chat_id", "")).strip()
            except (OSError, ValueError, TypeError):
                pass
        return token, chat_id

    @property
    def enabled(self):
        token, chat_id = self._credentials()
        return bool(token and chat_id)

    def status(self):
        token, chat_id = self._credentials()
        return {"configured": bool(token and chat_id),
                "token_present": bool(token), "chat_id_present": bool(chat_id),
                "last_error": self.last_error, "last_success_at": self.last_success_at}

    def configure(self, token, chat_id):
        token, chat_id = str(token or "").strip(), str(chat_id or "").strip()
        if not token or not chat_id:
            raise ValueError("Both bot token and chat ID are required")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.config_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"bot_token": token, "chat_id": chat_id}))
        try: os.chmod(temp, 0o600)
        except OSError: pass
        temp.replace(self.config_path)
        try: os.chmod(self.config_path, 0o600)
        except OSError: pass
        self._token_override = self._chat_override = None
        self.last_error = None
        return self.status()

    def _send(self, method, data, files=None):
        token, chat_id = self._credentials()
        if not token or not chat_id:
            self.last_error = "Telegram credentials are not configured"
            return False
        payload_data = dict(data)
        payload_data["chat_id"] = chat_id
        try:
            response = self.session.post(
                f"https://api.telegram.org/bot{token}/{method}",
                timeout=self.timeout, data=payload_data, files=files)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                self.last_error = (str(payload.get("description", "Telegram rejected request"))
                                   if isinstance(payload, dict) else "Invalid Telegram response")
                print("[NOTIFY] Telegram rejected request:", self.last_error)
                return False
            self.last_error = None
            self.last_success_at = time.time()
            return True
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {error}"
            print("[NOTIFY] Telegram send failed:", self.last_error)
            return False

    def send_message(self, text):
        return self._send("sendMessage", {"text": str(text)[:4000]})

    def send_photo(self, png_bytes, caption=""):
        return self._send("sendPhoto", {"caption": str(caption)[:1000]},
                          {"photo": ("trade.png", png_bytes, "image/png")})
