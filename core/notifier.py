"""Optional Telegram notifications (text + chart image). Off unless configured.

Environment: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Never raises.
"""
import os

import requests


class Notifier:

    def __init__(self, token=None, chat_id=None, session=None, timeout=15):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def enabled(self):
        return bool(self.token and self.chat_id)

    def _url(self, method):
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send_message(self, text):
        if not self.enabled:
            return False
        try:
            r = self.session.post(self._url("sendMessage"), timeout=self.timeout,
                                  data={"chat_id": self.chat_id, "text": text[:4000]})
            r.raise_for_status()
            payload = r.json()
            return isinstance(payload, dict) and payload.get("ok") is True
        except Exception as error:
            print("[NOTIFY] message failed:", type(error).__name__)
            return False

    def send_photo(self, png_bytes, caption=""):
        if not self.enabled:
            return False
        try:
            r = self.session.post(
                self._url("sendPhoto"), timeout=self.timeout,
                data={"chat_id": self.chat_id, "caption": caption[:1000]},
                files={"photo": ("trade.png", png_bytes, "image/png")})
            r.raise_for_status()
            payload = r.json()
            return isinstance(payload, dict) and payload.get("ok") is True
        except Exception as error:
            print("[NOTIFY] photo failed:", type(error).__name__)
            return False
