import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
 
# アクセストークン（BotFatherから発行されたアクセストークンに書き換えてください）
TOKEN = "7998030546:AAEI8FYuLMk61q3E2qG3Ck8lOFizQqlzO2Y"
 
 
class TelegramBot:
    def __init__(self, system):
        self.system = system

        # ロガーの設定
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        self.logger = logging.getLogger(__name__)

        self.app = ApplicationBuilder().token(TOKEN).build()
        self._register_handlers()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message)
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # 辞書型 inputにユーザIDを設定
        user_id = str(update.effective_user.id)
        input_dict = {'utt': None, 'sessionId': user_id}

        # システムからの最初の発話をinitial_messageから取得し，送信
        response = self.system.initial_message(input_dict)
        await update.message.reply_text(response.get("utt", ""))

    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # 辞書型 inputにユーザからの発話とユーザIDを設定
        user_id = str(update.effective_user.id)
        input_dict = {'utt': update.message.text, 'sessionId': user_id}

        # replyメソッドによりinputから発話を生成
        system_output = self.system.reply(input_dict)
        await update.message.reply_text(system_output.get("utt", ""))

    def run(self) -> None:
        self.logger.info("Bot is starting...")
        self.app.run_polling()


        
