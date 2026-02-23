"""
Главный файл Telegram бота для анализа аэрофотоснимков
"""
import asyncio
import logging
import sys
import selectors
import subprocess
from pathlib import Path
from telegram import Update
from telegram.error import TimedOut, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Устанавливаем SelectorEventLoop для Windows (требуется для psycopg)
if sys.platform == 'winчё32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from config import BOT_TOKEN, AVAILABLE_ALGORITHMS, LOCAL_BOT_API_URL, USE_LOCAL_BOT_API, TELEGRAM_MAX_FILE_SIZE, ALGORITHM_SERVER_URL
from handlers.command_handler import (
    start_command,
    help_command,
    cancel_command,
    show_algorithms,
    get_main_keyboard
)
from handlers.algorithm_handler import handle_algorithm_selection
from handlers.file_handler import handle_file
from database.db_session import init_db, close_db, AsyncSessionLocal

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

_algo_server_process: subprocess.Popen | None = None
_algo_server_pid_file = Path(__file__).with_name("algo_server.pid")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    user_text = update.message.text
    user_state = context.user_data.get('state')
    
    # Обработка главных кнопок
    if user_text == "📁 Отправить снимок":
        # Сразу просим прислать файл для анализа
        context.user_data['state'] = 'waiting_file'
        from handlers.algorithm_handler import get_file_upload_keyboard
        await update.message.reply_text(
            "📁 Пришлите снимок (как документ или фото) для анализа.",
            reply_markup=get_file_upload_keyboard()
        )
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
    
    if user_text == "🔄 Новый анализ" or user_text == "📁 Отправить другой снимок":
        context.user_data.clear()
        from handlers.algorithm_handler import get_file_upload_keyboard
        context.user_data['state'] = 'waiting_file'
        await update.message.reply_text(
            "📁 Пришлите следующий снимок для анализа.",
            reply_markup=get_file_upload_keyboard()
        )
        return
    
    # Обработка кнопок при ошибках
    if user_text == "🔄 Попробовать снова" or user_text.lower() in ['попробовать снова', 'retry']:
        context.user_data['state'] = 'waiting_file'
        from handlers.algorithm_handler import get_file_upload_keyboard
        await update.message.reply_text(
            "📁 Пришлите снимок для анализа ещё раз.",
            reply_markup=get_file_upload_keyboard()
        )
        return
    
    # Больше не поддерживаем выбор алгоритма, он один
    
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
    """Проверяет доступность локального HTTP-сервера (синхронно)"""
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=3) as response:
            # Даже если вернется 404, это значит сервер работает
            return True
    except urllib.error.HTTPError:
        # 404/401/etc — это тоже ответ сервера, значит он запущен
        return True
    except urllib.error.URLError:
        return False
    except Exception as e:
        logger.debug(f"Ошибка при проверке локального сервера: {e}")
        return False


def ensure_algorithm_server():
    """
    Проверяет доступность сервера алгоритмов и при необходимости
    пытается запустить его локально через uvicorn.
    """
    url = (ALGORITHM_SERVER_URL or "").rstrip("/")
    if not url:
        logger.warning("ALGORITHM_SERVER_URL не задан, сервер алгоритмов не будет запускаться автоматически")
        return

    # Если у нас остался PID от предыдущего автозапуска — гасим тот сервер, чтобы не было "старых" версий
    try:
        if _algo_server_pid_file.exists():
            pid_str = _algo_server_pid_file.read_text(encoding="utf-8").strip()
            if pid_str.isdigit():
                pid = int(pid_str)
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            _algo_server_pid_file.unlink(missing_ok=True)
    except Exception:
        # Не критично: просто не смогли прибраться
        pass

    # Если сервер уже отвечает - ничего не делаем
    if check_local_server_sync(url):
        logger.info(f"Сервер алгоритмов доступен по адресу {url}")
        return

    # Пытаемся распарсить host/port из URL
    host = "127.0.0.1"
    port = 8000
    try:
        without_scheme = url.split("://", 1)[-1]
        host_port = without_scheme.split("/", 1)[0]
        if ":" in host_port:
            host, port_str = host_port.split(":", 1)
            port = int(port_str)
        else:
            host = host_port
    except Exception:
        logger.warning(f"Не удалось корректно распарсить URL сервера алгоритмов: {url}, использую {host}:{port}")

    logger.info(f"Пробую запустить локальный сервер алгоритмов: host={host}, port={port}...")
    try:
        global _algo_server_process
        log_path = Path(__file__).with_name("algo_server.log")
        log_f = open(log_path, "a", encoding="utf-8")
        _algo_server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "algo_server:app", "--host", host, "--port", str(port)],
            cwd=str(Path(__file__).parent),
            stdout=log_f,
            stderr=log_f,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            _algo_server_pid_file.write_text(str(_algo_server_process.pid), encoding="utf-8")
        except Exception:
            pass
        # Даём серверу немного времени подняться
        import time
        time.sleep(2)
        if check_local_server_sync(url):
            logger.info("✅ Локальный сервер алгоритмов успешно запущен")
        else:
            logger.warning("⚠️ Не удалось подтвердить работу сервера алгоритмов после автозапуска")
    except Exception as e:
        logger.error(f"❌ Ошибка при автозапуске сервера алгоритмов: {e}", exc_info=True)


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

    # Проверяем/запускаем сервер алгоритмов
    ensure_algorithm_server()
    
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
    
    # Инициализируем базу данных при запуске
    async def post_init(app: Application) -> None:
        """Инициализация после создания приложения"""
        try:
            # Небольшая задержка для стабильности подключения
            import asyncio
            await asyncio.sleep(0.5)
            await init_db()
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}", exc_info=True)
            logger.warning("Бот продолжит работу без БД")
            logger.info("Проверьте параметры подключения в token.env и убедитесь, что PostgreSQL запущен")
    
    # Регистрируем функцию инициализации
    application.post_init = post_init
    
    # Функция для закрытия БД при завершении
    async def post_shutdown(app: Application) -> None:
        """Закрытие соединений при завершении"""
        try:
            await close_db()
            logger.info("Соединение с БД закрыто")
        except Exception as e:
            logger.error(f"Ошибка при закрытии БД: {e}")

        # Гасим сервер алгоритмов, если он был поднят этим ботом
        global _algo_server_process
        if _algo_server_process is not None:
            try:
                _algo_server_process.terminate()
                _algo_server_process.wait(timeout=5)
            except Exception:
                try:
                    _algo_server_process.kill()
                except Exception:
                    pass
            _algo_server_process = None
            try:
                _algo_server_pid_file.unlink(missing_ok=True)
            except Exception:
                pass
    
    application.post_shutdown = post_shutdown
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

