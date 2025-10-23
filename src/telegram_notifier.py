import telegram
import asyncio
from telegram.constants import ParseMode

class TelegramNotifier:
    """
    Lớp để gửi thông báo đến Telegram.
    """
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = None
        if self.bot_token and self.chat_id:
            try:
                self.bot = telegram.Bot(token=self.bot_token)
                print("[Telegram] Bot đã được khởi tạo.")
            except Exception as e:
                print(f"[Telegram] Lỗi khởi tạo bot: {e}")
        else:
            print("[Telegram] Bot Token hoặc Chat ID không được cung cấp. Thông báo Telegram sẽ bị tắt.")

    async def send_message_async(self, message):
        if self.bot:
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode=ParseMode.HTML)
            except Exception as e:
                print(f"[Telegram] Lỗi gửi tin nhắn: {e}")

    def send_message(self, message):
        if self.bot:
            asyncio.run(self.send_message_async(message))