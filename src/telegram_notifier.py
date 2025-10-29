import telegram
import asyncio
import threading
import queue

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        if not bot_token or not chat_id:
            raise ValueError("Bot token and chat ID cannot be empty.")
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = telegram.Bot(token=self.bot_token)
        self.message_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._message_worker, daemon=True)
        self.worker_thread.start()

    async def _send_message_async(self, message):
        """Hàm bất đồng bộ để gửi tin nhắn."""
        for _ in range(3): # Thử lại tối đa 3 lần
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='HTML')
                return
            except telegram.error.RetryAfter as e:
                print(f"[Telegram] Flood control: Thử lại sau {e.retry_after} giây.")
                await asyncio.sleep(e.retry_after)
            except Exception as e:
                print(f"[Telegram] Lỗi gửi tin nhắn: {e}")
                await asyncio.sleep(5) # Chờ 5 giây trước khi thử lại
        print(f"[Telegram] Gửi tin nhắn thất bại sau nhiều lần thử: {message[:50]}...")

    def _message_worker(self):
        """Luồng nền xử lý việc gửi tin nhắn từ hàng đợi."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while True:
                message = self.message_queue.get()
                if message is None: # Tín hiệu để dừng luồng
                    break
                loop.run_until_complete(self._send_message_async(message))
                self.message_queue.task_done()
        finally:
            loop.close()
            print("[Telegram] Event loop closed.")

    def send_message(self, message):
        """
        Thêm tin nhắn vào hàng đợi để được gửi đi bởi luồng nền.
        Hàm này không chặn và an toàn để gọi từ bất kỳ luồng nào.
        """
        self.message_queue.put(message)

    def stop(self):
        """Dừng luồng nền một cách an toàn."""
        self.message_queue.put(None)
        self.worker_thread.join()
        print("[Telegram] Đã dừng Notifier.")