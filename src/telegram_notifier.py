import asyncio
import threading
import time
import json
import urllib.request
import urllib.error
from typing import Optional

try:
    # Prefer python-telegram-bot if available for nicer shutdown/queue handling
    from telegram.ext import Application
    PTB_AVAILABLE = True
except Exception:
    Application = None
    PTB_AVAILABLE = False


class TelegramNotifier:
    """Robust Telegram notifier with two modes:
    - Preferred: use python-telegram-bot Application run in a background asyncio loop
    - Fallback: use direct HTTP requests to Telegram Bot API

    This ensures startup messages from `run_live.py` are sent even if PTB
    cannot be started in the current environment.
    """

    def __init__(self, bot_token: str, chat_id: str):
        if not bot_token or not chat_id:
            raise ValueError("Bot token and chat ID cannot be empty.")

        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.application = None
        self._loop = None
        self._loop_thread = None
        self._app_ready = threading.Event()  # Signal when app is fully initialized

        # Try to initialize PTB Application and start it on a dedicated loop thread
        if PTB_AVAILABLE:
            try:
                self.application = Application.builder().token(bot_token).build()

                # Create and run an event loop in a background thread
                self._loop = asyncio.new_event_loop()

                def _run_loop():
                    asyncio.set_event_loop(self._loop)
                    # start the application (job queue and bot become available)
                    # SỬA LỖI: Với python-telegram-bot v20+, cần gọi initialize() trước khi start()
                    try:
                        async def start_app():
                            await self.application.initialize()
                            await self.application.start()
                            self._app_ready.set()  # Signal that app is ready
                        
                        self._loop.run_until_complete(start_app())
                    except Exception as e:
                        print(f"[Telegram] Error while starting Application: {e}")
                    # Keep loop running to process job queue
                    try:
                        self._loop.run_forever()
                    finally:
                        # Cố gắng shutdown một cách tốt nhất
                        try:
                            self._loop.run_until_complete(self.application.shutdown())
                        except Exception:
                            pass

                self._loop_thread = threading.Thread(target=_run_loop, daemon=True)
                self._loop_thread.start()
                # Wait for application to be ready (with timeout)
                if self._app_ready.wait(timeout=3):
                    print("[Telegram] Notifier initialized (PTB mode).")
                else:
                    print("[Telegram] PTB Application startup timed out, will use HTTP fallback if needed.")
            except Exception as e:
                print(f"[Telegram] Failed to start PTB Application: {e}. Falling back to HTTP mode.")
                self.application = None

        else:
            print("[Telegram] python-telegram-bot not available, using HTTP fallback.")

    async def _send_job(self, context):
        """Job callback executed on the PTB job queue."""
        message = context.job.data
        try:
            await self.application.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='HTML')
        except Exception as e:
            print(f"[Telegram] Error sending message in job: {e}")

    def send_message(self, message: str) -> bool:
        """Send a message. Returns True on (apparent) success, False otherwise.

        Prefers using PTB job queue if available, otherwise falls back to HTTP send.
        """
        # Use PTB job queue if it's running
        try:
            if self.application and self._loop and self._app_ready.is_set():
                if self.application.job_queue and self.application.running:
                    # schedule the job on the running job queue
                    self.application.job_queue.run_once(self._send_job, 0, data=message)
                    return True
        except Exception as e:
            print(f"[Telegram] PTB job queue send failed: {e}")

        # If PTB mode is configured but not ready yet, give it one more chance
        if self.application and not self._app_ready.is_set():
            print(f"[Telegram] Waiting for PTB Application to initialize...")
            if self._app_ready.wait(timeout=1):
                try:
                    if self.application.job_queue and self.application.running:
                        self.application.job_queue.run_once(self._send_job, 0, data=message)
                        return True
                except Exception as e:
                    print(f"[Telegram] Second PTB attempt failed: {e}")

        # Fallback: direct HTTP send via Bot API
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = resp.read().decode('utf-8')
                # Quick check for ok flag
                try:
                    j = json.loads(resp_data)
                    if not j.get('ok', False):
                        print(f"[Telegram] HTTP send failed: {j}")
                        return False
                except Exception:
                    # If parsing fails, still accept this as an attempt
                    pass
            return True
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8')
            except Exception:
                body = '<no body>'
            print(f"[Telegram] HTTPError sending message: {e.code} {e.reason} - {body}")
            return False
        except Exception as e:
            print(f"[Telegram] Exception in HTTP fallback send: {e}")
            return False

    def shutdown_sync(self):
        """Shutdown the notifier cleanly.

        If PTB Application is running, stop the job queue and application and stop the loop thread.
        """
        if self.application and self._loop and self._loop_thread:
            print("[Telegram] Shutting down PTB Application...")
            try:
                # stop job queue and shutdown application via run_coroutine_threadsafe
                from concurrent.futures import TimeoutError
                import asyncio as _asyncio

                fut1 = _asyncio.run_coroutine_threadsafe(self.application.job_queue.stop(), self._loop)
                fut1.result(timeout=5)
                fut2 = _asyncio.run_coroutine_threadsafe(self.application.shutdown(), self._loop)
                fut2.result(timeout=5)
            except Exception as e:
                print(f"[Telegram] Error during PTB shutdown: {e}")
            try:
                # stop the loop
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._loop_thread.join(timeout=2)
            except Exception:
                pass
            print("[Telegram] Notifier shutdown complete.")
        else:
            print("[Telegram] No PTB Application to shutdown (or using HTTP fallback).")