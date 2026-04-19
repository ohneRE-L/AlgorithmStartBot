"""
Обработчики команд бота
"""
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import AVAILABLE_ALGORITHMS, TELEGRAM_MAX_FILE_SIZE, USE_LOCAL_BOT_API
from database.db_session import AsyncSessionLocal
from database.repository import UserRepository, RequestRepository

logger = logging.getLogger(__name__)


def get_main_keyboard(user_role='OPERATOR'):
    """Главная клавиатура: разные кнопки в зависимости от логики"""
    keyboard = [
        [KeyboardButton("📁 Отправить снимок")],
        [KeyboardButton("📋 Мои задачи")],
        [KeyboardButton("❓ Помощь")]
    ]
    if user_role == 'MODERATOR':
        keyboard.append([KeyboardButton("🛡 Очередь задач"), KeyboardButton("📈 Аналитика")])
        
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


def get_file_upload_keyboard():
    """Клавиатура при ожидании загрузки файла"""
    max_size_mb = int(TELEGRAM_MAX_FILE_SIZE / (1024 * 1024))
    api_info = "локальный сервер Bot API" if USE_LOCAL_BOT_API else "Telegram Bot API"
    
    keyboard = [
        [KeyboardButton("📁 Отправить другой снимок")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    # Регистрируем или обновляем пользователя в БД
    user_role = 'OPERATOR'
    try:
        async with AsyncSessionLocal() as session:
            user = await UserRepository.get_or_create_user(
                session=session,
                telegram_id=update.effective_user.id,
                username=update.effective_user.username
            )
            user_role = user.role
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
        reply_markup=get_main_keyboard(user_role)
    )
    
    # Сбрасываем состояние пользователя и сохраняем роль
    context.user_data.clear()
    context.user_data['role'] = user_role

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




async def my_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображение задач пользователя"""
    user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        tasks = await RequestRepository.get_user_tasks(session, user_id)
        
        if not tasks:
            await update.message.reply_text("У вас пока нет задач.")
            return
            
        msg = "📋 *Список ваших задач (последние 20):*\n\n"
        keyboard = []
        for i, t in enumerate(tasks[:20], 1):
            s_map = {
                'PENDING': ('⏳', 'В очереди'),
                'PROCESSING': ('⚙️', 'Обработка'),
                'COMPLETED': ('✅', 'Готово'),
                'ERROR': ('❌', 'Ошибка'),
                'PENDING_MODERATION': ('🛡', 'Модерация'),
                'REJECTED': ('🚫', 'Отклонено'),
                'CANCELLED': ('🛑', 'Отмена')
            }
            emoji, status_text = s_map.get(t.status, ('🔹', t.status))
            date_str = t.created_at.strftime('%d.%m %H:%M') if t.created_at else "??.?"
            
            # Компактная строка
            msg += f"{emoji} *#{i}* [{date_str}] — {status_text}\n"
            msg += f"   `...{str(t.id)[-8:]}`\n\n"
            
            if t.status in ['PENDING', 'PENDING_MODERATION']:
                keyboard.append([InlineKeyboardButton(f"❌ Отменить #{i}", callback_data=f"optcancel_{t.id}")])
            
        if len(tasks) > 20:
            msg += f"...и еще {len(tasks)-20} задач(и)"
            
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)


async def setmod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Секретная команда для быстрого получения прав модератора"""
    user_id = update.effective_user.id
    try:
        async with AsyncSessionLocal() as session:
            user = await UserRepository.get_or_create_user(session, user_id, update.effective_user.username)
            user.role = 'MODERATOR'
            await session.commit()
            
        context.user_data['role'] = 'MODERATOR'
        await update.message.reply_text("✅ Теперь вы МОДЕРАТОР. Ваше меню обновлено.", reply_markup=get_main_keyboard('MODERATOR'))
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def handle_operator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок оператора (например, отмена)"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("optcancel_"):
        request_id = data.split("_", 1)[1]
        user_id = update.effective_user.id
        
        async with AsyncSessionLocal() as session:
            success = await RequestRepository.cancel_request(session, request_id, user_id)
            if success:
                await query.edit_message_text(f"✅ Успешно! Заявка `{request_id}` отменена.\n\nНажмите «Мои задачи» чтобы получить обновленный список.", parse_mode="Markdown")
            else:
                await query.answer("❌ Заявка не найдена или уже не может быть отменена.", show_alert=True)


async def cancel_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет задачу"""
    if not context.args:
        await update.message.reply_text("Использование: /cancel_task <ID_заявки>")
        return
        
    request_id = context.args[0]
    user_id = update.effective_user.id
    
    async with AsyncSessionLocal() as session:
        success = await RequestRepository.cancel_request(session, request_id, user_id)
        if success:
            await update.message.reply_text(f"✅ Заявка {request_id} отменена.")
        else:
            await update.message.reply_text("❌ Заявка не найдена или уже не может быть отменена (например, её анализ уже завершён).")

