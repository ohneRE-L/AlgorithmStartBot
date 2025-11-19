"""
Обработчики команд бота
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from config import AVAILABLE_ALGORITHMS


def get_main_keyboard():
    """Возвращает главную клавиатуру"""
    keyboard = [
        [KeyboardButton("📋 Выбрать алгоритм")],
        [KeyboardButton("❓ Помощь"), KeyboardButton("❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_error_keyboard():
    """Возвращает клавиатуру при ошибке"""
    keyboard = [
        [KeyboardButton("🔄 Попробовать снова")],
        [KeyboardButton("📋 Выбрать другой алгоритм")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_after_result_keyboard():
    """Возвращает клавиатуру после получения результата"""
    keyboard = [
        [KeyboardButton("🔄 Новый анализ")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_message = (
        "👋 Добро пожаловать в бот для анализа аэрофотоснимков!\n\n"
        "Я помогу вам запустить анализ данных с БПЛА.\n\n"
        "Для начала работы выберите алгоритм из списка."
    )
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_main_keyboard()
    )
    
    # Сбрасываем состояние пользователя
    context.user_data.clear()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📖 Справка по использованию бота:\n\n"
        "1. Используйте кнопку 'Выбрать алгоритм' для начала работы\n"
        "2. Выберите нужный алгоритм из списка\n"
        "3. Загрузите файл с данными (поддерживаются форматы: .tif, .tiff, .geotiff, .jpg, .jpeg, .png)\n"
        "4. Дождитесь завершения анализа\n"
        "5. Получите результат в чате\n\n"
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
    message = "📋 Выберите алгоритм для анализа:\n\n"
    
    keyboard = []
    for key, algo in AVAILABLE_ALGORITHMS.items():
        message += f"{key}. {algo['name']}\n   {algo['description']}\n\n"
        keyboard.append([KeyboardButton(f"{key}. {algo['name']}")])
    
    # Добавляем кнопку "Назад"
    keyboard.append([KeyboardButton("🔙 Назад")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup
    )
    
    # Устанавливаем состояние ожидания выбора алгоритма
    context.user_data['state'] = 'waiting_algorithm'

