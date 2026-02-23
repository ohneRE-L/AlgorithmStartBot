"""
Обработчики выбора алгоритма
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from config import AVAILABLE_ALGORITHMS, TELEGRAM_MAX_FILE_SIZE, USE_LOCAL_BOT_API
from handlers.command_handler import show_algorithms, get_main_keyboard


def get_file_upload_keyboard():
    """Клавиатура при ожидании загрузки файла"""
    keyboard = [
        [KeyboardButton("📁 Отправить другой снимок")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def handle_algorithm_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает выбранный (единственный) алгоритм и просит прислать файл"""
    user_text = update.message.text
    
    # Обработка кнопки "Назад"
    if user_text == "🔙 Назад" or user_text.lower() in ['назад', 'back']:
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 Возврат в главное меню",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Ищем выбранный алгоритм
    selected_algorithm = None
    for key, algo in AVAILABLE_ALGORITHMS.items():
        if user_text.startswith(key) or user_text == algo['name']:
            selected_algorithm = algo
            break
    
    if selected_algorithm is None:
        await update.message.reply_text(
            "❌ Алгоритм не распознан. Пожалуйста, выберите алгоритм из списка."
        )
        return
    
    # Сохраняем выбранный алгоритм
    context.user_data['selected_algorithm'] = selected_algorithm
    context.user_data['state'] = 'waiting_file'
    
    # Просим загрузить файл с кнопками
    max_size_mb = int(TELEGRAM_MAX_FILE_SIZE / (1024 * 1024))
    api_info = "локальный сервер Bot API" if USE_LOCAL_BOT_API else "Telegram Bot API"
    
    await update.message.reply_text(
        f"✅ Выбран алгоритм: {selected_algorithm['name']}\n\n"
        f"📁 Теперь загрузите файл с данными для анализа.\n\n"
        f"Поддерживаемые форматы: .tif, .tiff, .geotiff, .jpg, .jpeg, .png\n"
        f"Максимальный размер: {max_size_mb} МБ ({api_info})",
        reply_markup=get_file_upload_keyboard()
    )

