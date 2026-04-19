import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.db_session import AsyncSessionLocal
from database.repository import RequestRepository, ResultRepository, UserRepository

logger = logging.getLogger(__name__)

def get_moderation_keyboard(request_id: str):
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"mod_approve_{request_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"mod_reject_{request_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("mod_"):
        return

    tokens = data.split("_")
    if len(tokens) < 3:
        return
        
    action = tokens[1] # approve или reject
    request_id = tokens[2]

    async with AsyncSessionLocal() as session:
        req = await RequestRepository.get_request_by_id(session, request_id)
        if not req:
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n⚠️ Заявка не найдена.")
            return

        if req.status != 'PENDING_MODERATION':
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n⚠️ Заявка уже была обработана ({req.status}).")
            return

        user_id = req.user_id
        
        if action == "approve":
            await RequestRepository.update_status(session, request_id, 'COMPLETED')
            new_status_text = "✅ Одобрено"
            
            # Отправляем результат пользователю
            result = await ResultRepository.get_result_by_request(session, request_id)
            if result and "file_generated" in result.result_metadata:
                file_path = result.result_metadata["file_generated"]
                try:
                    with open(file_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=user_id,
                            document=f,
                            caption="✅ Ваш снимок успешно прошел модерацию и анализ завершен."
                        )
                    try:
                        os.remove(file_path)
                    except:
                        pass
                except Exception as e:
                    logger.error(f"Error sending file to user {user_id}: {e}")
                    await context.bot.send_message(chat_id=user_id, text="⚠️ Результат одобрен, но файл не найден.")
            else:
                await context.bot.send_message(chat_id=user_id, text="✅ Ваш снимок прошел модерацию, но результата нет.")

        elif action == "reject":
            await RequestRepository.update_status(session, request_id, 'REJECTED')
            new_status_text = "❌ Отклонено"
            
            # Удалять файл тоже можно
            result = await ResultRepository.get_result_by_request(session, request_id)
            if result and "file_generated" in result.result_metadata:
                file_path = result.result_metadata["file_generated"]
                try:
                    os.remove(file_path)
                except:
                    pass
            
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ваш снимок был отклонен модератором (например, из-за плохого качества)."
            )

        new_caption = f"{query.message.caption}\n\n{new_status_text} (@{update.effective_user.username or update.effective_user.id})"
        await query.edit_message_caption(caption=new_caption, reply_markup=None)

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user = await UserRepository.get_or_create_user(session, user_id)
        if user.role != 'MODERATOR':
            await update.message.reply_text("⛔ Эта команда доступна только модераторам.")
            return
            
        tasks = await RequestRepository.get_all_tasks(session)
        pending = [t for t in tasks if t.status == 'PENDING_MODERATION']
        
        if not pending:
            await update.message.reply_text("✅ Очередь на модерацию пуста.")
            return
            
        msg = f"📊 *Очередь на модерацию ({len(pending)}):*\n\n"
        for t in pending[:10]:
            msg += f"🔹 Заявка `{t.id}`\n"
            msg += f"   От: {t.user_id}\n"
            msg += f"   Алгоритм: {t.algorithm_name}\n"
            msg += f"   Дата: {t.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
        if len(pending) > 10:
             msg += f"...и еще {len(pending)-10} задач"
             
        await update.message.reply_markdown(msg)

async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with AsyncSessionLocal() as session:
        user = await UserRepository.get_or_create_user(session, user_id)
        if user.role != 'MODERATOR':
            await update.message.reply_text("⛔ Эта команда доступна только модераторам.")
            return
            
        stats = await RequestRepository.get_tasks_stats(session)
        
        msg = "📈 *Аналитика задач:*\n\n"
        msg += f"Всего заявок: {stats['total']}\n"
        for st, count in stats['by_status'].items():
            # escape - for markdown v2, or just use bold appropriately
            msg += f" * {st}: {count}\n"
            
        await update.message.reply_markdown(msg)
