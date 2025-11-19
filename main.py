"""
Главный файл Telegram бота для анализа аэрофотоснимков
"""
import asyncio
import logging
from telegram import Update
from telegram.error import TimedOut, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from config import BOT_TOKEN, AVAILABLE_ALGORITHMS, LOCAL_BOT_API_URL, USE_LOCAL_BOT_API, TELEGRAM_MAX_FILE_SIZE
from handlers.command_handler import (
    start_command,
    help_command,
    cancel_command,
    show_algorithms,
    get_main_keyboard
)
from handlers.algorithm_handler import handle_algorithm_selection
from handlers.file_handler import handle_file

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    user_text = update.message.text
    user_state = context.user_data.get('state')
    
    # Обработка главных кнопок
    if user_text == "📋 Выбрать алгоритм" or user_text.lower() in ['выбрать алгоритм', 'алгоритм']:
        await show_algorithms(update, context)
        return
    
    if user_text == "❓ Помощь" or user_text.lower() in ['помощь', 'help']:
        await help_command(update, context)
        return
    
    if user_text == "❌ Отмена" or user_text.lower() in ['отмена', 'cancel']:
        await cancel_command(update, context)
        return
    
    if user_text == "🏠 Главное меню" or user_text.lower() in ['главное меню', 'меню', 'home']:
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=get_main_keyboard()
        )
        return
    
    if user_text == "🔄 Новый анализ" or user_text.lower() in ['новый анализ', 'new']:
        context.user_data.clear()
        await show_algorithms(update, context)
        return
    
    # Обработка кнопок при ошибках
    if user_text == "🔄 Попробовать снова" or user_text.lower() in ['попробовать снова', 'retry']:
        if 'selected_algorithm' in context.user_data:
            context.user_data['state'] = 'waiting_file'
            from handlers.algorithm_handler import get_file_upload_keyboard
            await update.message.reply_text(
                "📁 Загрузите файл с данными для анализа.",
                reply_markup=get_file_upload_keyboard()
            )
        else:
            await show_algorithms(update, context)
        return
    
    if user_text == "📋 Выбрать другой алгоритм":
        context.user_data.pop('selected_algorithm', None)
        await show_algorithms(update, context)
        return
    
    # Обработка выбора алгоритма
    if user_state == 'waiting_algorithm':
        await handle_algorithm_selection(update, context)
        return
    
    # Обработка кнопок при ожидании файла (обрабатывается в file_handler)
    if user_state == 'waiting_file':
        # Проверяем, не является ли это кнопкой
        if user_text in ["🔙 Выбрать другой алгоритм", "❌ Отмена"]:
            await handle_file(update, context)
            return
    
    # Если состояние не определено, предлагаем начать заново
    await update.message.reply_text(
        "Не понимаю команду. Используйте кнопки для навигации.",
        reply_markup=get_main_keyboard()
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Если это ошибка таймаута или сети, пытаемся отправить сообщение пользователю
    if isinstance(context.error, (TimedOut, NetworkError)):
        logger.warning(f"Network error: {context.error}")
        if update and isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Произошла временная ошибка сети. Пожалуйста, попробуйте еще раз.",
                    reply_markup=get_main_keyboard()
                )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
    elif isinstance(context.error, TelegramError):
        logger.error(f"Telegram error: {context.error}")
        if update and isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ Произошла ошибка при обработке запроса. Попробуйте еще раз или используйте /start.",
                    reply_markup=get_main_keyboard()
                )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")


def check_local_server_sync(url: str) -> bool:
    """Проверяет доступность локального сервера Bot API (синхронно)"""
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=3) as response:
            # Даже если вернется 404, это значит сервер работает
            return True
    except urllib.error.URLError:
        return False
    except Exception as e:
        logger.debug(f"Ошибка при проверке локального сервера: {e}")
        return False


def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Создайте файл token.env и добавьте BOT_TOKEN=ваш_токен")
        return
    
    # Если используется локальный сервер Bot API, проверяем его доступность
    if USE_LOCAL_BOT_API:
        logger.info(f"Проверяю доступность локального сервера Bot API: {LOCAL_BOT_API_URL}")
        is_available = check_local_server_sync(LOCAL_BOT_API_URL)
        
        if not is_available:
            logger.error(
                f"❌ Локальный сервер Bot API недоступен по адресу {LOCAL_BOT_API_URL}\n\n"
                "Убедитесь, что:\n"
                "1. Локальный сервер Bot API запущен\n"
                "2. Сервер работает на правильном порту (по умолчанию 8081)\n"
                "3. URL в token.env правильный\n\n"
                "Для запуска локального сервера выполните:\n"
                "telegram-bot-api --local --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH\n\n"
                "Или уберите LOCAL_BOT_API_URL из token.env для использования официального API"
            )
            return
    
    # Создаем приложение
    builder = Application.builder().token(BOT_TOKEN)
    
    # Если используется локальный сервер Bot API, настраиваем его
    if USE_LOCAL_BOT_API:
        logger.info(f"✅ Используется локальный сервер Bot API: {LOCAL_BOT_API_URL}")
        # Устанавливаем базовый URL для локального сервера
        builder = builder.base_url(f"{LOCAL_BOT_API_URL}/bot")
        logger.info(f"Максимальный размер файла: {TELEGRAM_MAX_FILE_SIZE / (1024*1024):.0f} МБ")
    else:
        logger.info("Используется официальный Telegram Bot API")
        logger.info(f"Максимальный размер файла: {TELEGRAM_MAX_FILE_SIZE / (1024*1024):.0f} МБ")
    
    application = builder.build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Обработчик файлов (документы и фото)
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO,
        handle_file
    ))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

