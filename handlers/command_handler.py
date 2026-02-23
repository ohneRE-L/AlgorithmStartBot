"""
Обработчики команд бота
"""
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from config import AVAILABLE_ALGORITHMS
from database.db_session import AsyncSessionLocal
from database.repository import UserRepository

logger = logging.getLogger(__name__)


def get_main_keyboard():
    """Главная клавиатура: сразу просим прислать снимок или открыть справку"""
    keyboard = [
        [KeyboardButton("📁 Отправить снимок")],
        [KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_error_keyboard():
    """Клавиатура при ошибке"""
    keyboard = [
        [KeyboardButton("🔄 Попробовать снова")],
        [KeyboardButton("📁 Отправить другой снимок")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_after_result_keyboard():
    """Клавиатура после получения результата"""
    keyboard = [
        [KeyboardButton("🔄 Новый анализ")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    # Регистрируем или обновляем пользователя в БД
    try:
        async with AsyncSessionLocal() as session:
            user = await UserRepository.get_or_create_user(
                session=session,
                telegram_id=update.effective_user.id,
                username=update.effective_user.username,
                full_name=update.effective_user.full_name
            )
            logger.info(f"User {user.telegram_id} ({user.username}) started the bot")
    except Exception as e:
        logger.error(f"Error registering user: {e}", exc_info=True)
        # Продолжаем работу даже если не удалось зарегистрировать пользователя
    
    welcome_message = (
        "👋 Добро пожаловать в бот для анализа аэрофотоснимков!\n\n"
        "Я запущу сегментацию земель по вашему снимку с помощью модели OEM-Lightweight.\n\n"
        "Нажмите «📁 Отправить снимок» и приложите файл (или просто пришлите снимок как документ/фото)."
    )
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_main_keyboard()
    )
    
    # Сбрасываем состояние пользователя
    context.user_data.clear()

    # Единственный алгоритм выбираем автоматически
    try:
        context.user_data['selected_algorithm'] = next(iter(AVAILABLE_ALGORITHMS.values()))
    except StopIteration:
        pass


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📖 Справка по использованию бота:\n\n"
        "1. Нажмите кнопку «📁 Отправить снимок» или просто пришлите файл со снимком.\n"
        "2. Бот проверит файл и запустит алгоритм OEM-Lightweight для сегментации земель.\n"
        "3. Дождитесь завершения анализа и получите результат в виде изображения.\n\n"
        "Команды:\n"
        "/start - начать работу\n"
        "/help - показать эту справку\n"
        "/cancel - отменить текущую операцию"
    )
    
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Операция отменена.",
        reply_markup=get_main_keyboard()
    )


async def show_algorithms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список доступных алгоритмов"""
    message = "📋 Доступен алгоритм анализа на основе OEM-Lightweight:\n\n"
    
    keyboard = []
    for key, algo in AVAILABLE_ALGORITHMS.items():
        message += f"{key}. {algo['name']}\n   {algo['description']}\n\n"
        keyboard.append([KeyboardButton(algo['name'])])
    
    # Добавляем кнопку "Назад"
    keyboard.append([KeyboardButton("🔙 Назад")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup
    )
    
    # Устанавливаем состояние ожидания выбора алгоритма
    context.user_data['state'] = 'waiting_algorithm'

