import os
import asyncio
import logging
from telegram import Update
from telegram.error import TelegramError, TimedOut, NetworkError, BadRequest
from telegram.ext import ContextTypes
from utils.file_validator import validate_file
from server_client import AlgorithmServerClient
from config import (
    TELEGRAM_MAX_FILE_SIZE,
    USE_LOCAL_BOT_API,
    AVAILABLE_ALGORITHMS,
    FILE_DOWNLOAD_READ_TIMEOUT,
    FILE_DOWNLOAD_WRITE_TIMEOUT,
    FILE_DOWNLOAD_CONNECT_TIMEOUT,
)
from handlers.command_handler import (
    get_error_keyboard,
    get_main_keyboard,
    get_after_result_keyboard,
)
from database.db_session import AsyncSessionLocal
from database.repository import UserRepository, RequestRepository, ResultRepository
from handlers.moderator_handler import get_moderation_keyboard

logger = logging.getLogger(__name__)


async def _safe_edit_or_reply(processing_msg, update: Update, text: str, reply_markup=None):
    """Обновляет сообщение или отправляет новое, если edit вернул 400 (например, тот же текст)."""
    if not processing_msg:
        await update.message.reply_text(text, reply_markup=reply_markup)
        return
    try:
        if reply_markup is not None:
            await processing_msg.edit_text(text, reply_markup=reply_markup)
        else:
            await processing_msg.edit_text(text)
    except BadRequest:
        await update.message.reply_text(text, reply_markup=reply_markup)
    except TelegramError:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text if update.message.text else ""

    if user_text == "🏠 Главное меню":
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=get_main_keyboard()
        )
        return

    if context.user_data.get('state') != 'waiting_file':
        # Если состояние не определено, просим начать заново с главной клавиатурой
        await update.message.reply_text(
            "Для анализа сначала нажмите «📁 Отправить снимок» или используйте /start.",
            reply_markup=get_main_keyboard()
        )
        return

    is_photo = False
    if update.message.document:
        file = update.message.document
    elif update.message.photo:
        file = update.message.photo[-1]
        is_photo = True
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте файл как документ или фото."
        )
        return

    file_size = getattr(file, 'file_size', 0)
    if file_size and file_size > TELEGRAM_MAX_FILE_SIZE:
        file_size_mb = file_size / (1024 * 1024)
        max_size_mb = int(TELEGRAM_MAX_FILE_SIZE / (1024 * 1024))
        api_info = "локального сервера Bot API" if USE_LOCAL_BOT_API else "Telegram Bot API"
        await update.message.reply_text(
            f"❌ Файл слишком большой для обработки.\n\n"
            f"Размер файла: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер для скачивания: {max_size_mb} МБ ({api_info})\n\n"
            f"Пожалуйста, загрузите файл меньшего размера или используйте сжатие.",
            reply_markup=get_error_keyboard()
        )
        context.user_data['state'] = 'waiting_file'
        return

    processing_msg = None
    try:
        processing_msg = await update.message.reply_text("⏳ Проверяю файл...")
    except Exception:
        pass

    try:
        # Если алгоритм не задан (у нас он один), подставляем автоматически
        if 'selected_algorithm' not in context.user_data:
            try:
                context.user_data['selected_algorithm'] = next(iter(AVAILABLE_ALGORITHMS.values()))
            except StopIteration:
                context.user_data['selected_algorithm'] = {
                    "id": "agriculture_classification",
                    "name": "OEM-Lightweight",
                }

        download_kw = dict(
            read_timeout=FILE_DOWNLOAD_READ_TIMEOUT,
            write_timeout=FILE_DOWNLOAD_WRITE_TIMEOUT,
            connect_timeout=FILE_DOWNLOAD_CONNECT_TIMEOUT,
        )
        try:
            file_obj = await context.bot.get_file(file.file_id, **download_kw)
        except TelegramError as e:
            error_msg = str(e)
            logger.error(f"Error getting file: {error_msg}")
            error_text = f"❌ Ошибка при получении файла:\n{error_msg}\nПопробуйте загрузить файл снова."
            await _safe_edit_or_reply(processing_msg, update, error_text, reply_markup=get_error_keyboard())
            context.user_data['state'] = 'waiting_file'
            return

        if is_photo:
            file_name = f"photo_{file.file_id}.jpg"
        else:
            file_name = getattr(file, 'file_name', None) or f"file_{file.file_id}"

        download_path = f"downloads/{update.effective_user.id}_{file_name}"
        os.makedirs('downloads', exist_ok=True)

        # Для больших файлов показываем, что идёт скачивание (может занять минуты)
        await _safe_edit_or_reply(
            processing_msg, update,
            "⏳ Скачиваю файл... (для файлов 100+ МБ это может занять несколько минут)"
        )

        logger.info(f"Starting file download: {file_name}, size: {file_size} bytes")
        try:
            await file_obj.download_to_drive(download_path, **download_kw)
        except (TimedOut, NetworkError, TelegramError) as e:
            logger.error(f"Download failed: {e}")
            await _safe_edit_or_reply(
                processing_msg, update,
                f"❌ Ошибка при скачивании файла:\n{e}\n\nПопробуйте отправить файл снова.",
                reply_markup=get_error_keyboard()
            )
            context.user_data['state'] = 'waiting_file'
            return

        # Получаем реальный размер файла после скачивания
        real_file_size = os.path.getsize(download_path)
        is_valid, error_message = validate_file(download_path, real_file_size)

        if not is_valid:
            error_text = f"❌ Ошибка проверки файла:\n{error_message}\n\nВыберите действие:"
            await _safe_edit_or_reply(processing_msg, update, error_text, reply_markup=get_error_keyboard())
            try:
                os.remove(download_path)
            except:
                pass
            context.user_data['state'] = 'waiting_file'
            return

        status_text = "✅ Файл проверен и готов к обработке.\n🚀 Запускаю анализ на сервере..."
        await _safe_edit_or_reply(processing_msg, update, status_text)

        # Работа с БД
        db_request = None
        user_id = update.effective_user.id
        algo_name = context.user_data['selected_algorithm'].get('name', "OEM-Lightweight")

        try:
            async with AsyncSessionLocal() as session:
                # Гарантируем, что юзер есть
                await UserRepository.get_or_create_user(
                    session=session,
                    telegram_id=user_id,
                    username=update.effective_user.username
                )

                # Создаем заявку (AnalysisRequest) и запись о файле
                db_request = await RequestRepository.create_analysis_request(
                    session=session,
                    user_id=user_id,
                    file_path=download_path,
                    file_size=real_file_size,
                    algorithm_name=algo_name
                )
                request_id = str(db_request.id)
                logger.info(f"Created request in DB: {request_id}")
        except Exception as e:
            logger.error(f"Error creating request in DB: {e}", exc_info=True)
            if processing_msg:
                await processing_msg.edit_text("❌ Ошибка базы данных.", reply_markup=get_error_keyboard())
            return

        # Работа с сервером алгоритмов
        client = AlgorithmServerClient()
        algorithm_id = context.user_data['selected_algorithm'].get('id', "agriculture_classification")
        success, server_task_id, error = await client.start_analysis(
            algorithm_id,
            download_path,
            user_id
        )

        if not success:
            try:
                async with AsyncSessionLocal() as session:
                    await RequestRepository.update_status(
                        session=session,
                        request_id=request_id,
                        status='ERROR'
                    )
            except Exception:
                pass

            error_text = f"❌ Ошибка при запуске анализа:\n{error}\n\nВыберите действие:"
            if processing_msg:
                try:
                    await processing_msg.edit_text(error_text, reply_markup=get_error_keyboard())
                except:
                    pass
            await client.close()
            context.user_data['state'] = 'error'
            return

        # Обновляем статус на PROCESSING
        try:
            async with AsyncSessionLocal() as session:
                await RequestRepository.update_status(
                    session=session,
                    request_id=request_id,
                    status='PROCESSING'
                )
        except Exception:
            pass

        context.user_data['db_request_id'] = request_id
        context.user_data['server_task_id'] = server_task_id
        context.user_data['file_path'] = download_path
        context.user_data['state'] = 'processing'

        success_text = f"✅ Анализ запущен!\n📋 ID заявки: {request_id}\n\n⏳ Ожидаю завершения анализа..."
        if processing_msg:
            try:
                await processing_msg.edit_text(success_text)
            except:
                pass

        await client.close()
        asyncio.create_task(
            monitor_task_status(update, context, server_task_id, download_path, request_id, processing_msg)
        )

    except Exception as e:
        logger.error(f"Unexpected error in handle_file: {e}", exc_info=True)
        await _safe_edit_or_reply(
            processing_msg, update,
            "❌ Произошла непредвиденная ошибка.",
            reply_markup=get_error_keyboard()
        )
        context.user_data['state'] = 'error'


async def monitor_task_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        server_task_id: str,
        file_path: str,
        db_request_id: str = None,
        processing_msg = None
):
    client = AlgorithmServerClient()
    max_attempts = 60
    attempt = 0
    try:
        status_map = {
            'processing': 'PROCESSING',
            'completed': 'COMPLETED',
            'failed': 'ERROR',
            'queued': 'PENDING'
        }
        while attempt < max_attempts:
            await asyncio.sleep(5)
            status, error = await client.check_status(server_task_id)
            attempt += 1

            if db_request_id and status:
                try:
                    async with AsyncSessionLocal() as session:
                        db_status = status_map.get(status, 'PROCESSING')
                        await RequestRepository.update_status(
                            session=session,
                            request_id=db_request_id,
                            status=db_status
                        )
                except Exception as e:
                    logger.error(f"Error updating DB status: {e}")

            if error:
                await _safe_edit_or_reply(
                    processing_msg, update,
                    f"❌ Ошибка при проверке статуса:\n{error}\n\nВыберите действие:",
                    reply_markup=get_error_keyboard()
                )
                if db_request_id:
                    async with AsyncSessionLocal() as session:
                        await RequestRepository.update_status(session, db_request_id, 'ERROR')
                context.user_data.clear()
                break

            if status == 'completed':
                await _safe_edit_or_reply(processing_msg, update, "✅ Анализ завершен! Получаю результат...")
                success, result_path, error = await client.get_result(server_task_id)

                if success:
                    # Пытаемся получить статистику по классам
                    stats_success, stats, stats_err = await client.get_stats(server_task_id)
                    summary_lines = []
                    if stats_success and stats:
                        for item in stats:
                            name = item.get("name", "unknown")
                            p = item.get("percent", 0.0)
                            summary_lines.append(f"- {name}: {p:.1f}%")
                    elif stats_err:
                        logger.warning(f"Не удалось получить статистику по классам: {stats_err}")

                    # 1. Сохраняем результат в БД
                    if db_request_id:
                        try:
                            async with AsyncSessionLocal() as session:
                                await RequestRepository.update_status(session, db_request_id, 'PENDING_MODERATION')
                                # Создаем метаданные для примера
                                meta = {
                                    "status": "success",
                                    "file_generated": result_path,
                                    "algorithm": context.user_data.get('selected_algorithm', {}).get('name')
                                }
                                await ResultRepository.create_result(
                                    session=session,
                                    request_id=db_request_id,
                                    metadata=meta
                                )
                                
                                # Отправляем всем модераторам на проверку
                                moderators = await UserRepository.get_all_moderators(session)
                                if moderators:
                                    caption_lines = [
                                        f"🛡 <b>Новая заявка на модерацию</b>",
                                        f"ID: {db_request_id}",
                                        f"Пользователь: {update.effective_user.id}",
                                        f"Алгоритм: {context.user_data.get('selected_algorithm', {}).get('name', 'N/A')}",
                                        "", "Статистика:"
                                    ]
                                    caption_lines.extend(summary_lines)
                                    caption = "\n".join(caption_lines)
                                    
                                    for mod in moderators:
                                        try:
                                            with open(result_path, 'rb') as f:
                                                await context.bot.send_photo(
                                                    chat_id=mod.telegram_id,
                                                    photo=f,
                                                    caption=caption,
                                                    reply_markup=get_moderation_keyboard(db_request_id),
                                                    parse_mode="HTML"
                                                )
                                        except Exception as e:
                                            logger.error(f"Failed to send to moderator {mod.telegram_id}: {e}")

                        except Exception as e:
                            logger.error(f"Error saving result to DB or notifying mods: {e}", exc_info=True)

                    # 2. Уведомляем пользователя
                    await _safe_edit_or_reply(
                        processing_msg, update,
                        "✅ Анализ на сервере завершен.\n⏳ Ваш снимок сейчас находится на проверке у специалиста (модератора).\nВы получите уведомление как только он будет одобрен.",
                        reply_markup=get_main_keyboard()
                    )

                    # Чистим только ИСХОДНЫЙ файл
                    try:
                        os.remove(file_path)
                        # result_path НЕ УДАЛЯЕМ, пока модератор не проверит
                    except:
                        pass
                else:
                    await _safe_edit_or_reply(
                        processing_msg, update,
                        f"❌ Не удалось скачать результат: {error}",
                        reply_markup=get_error_keyboard()
                    )
                    if db_request_id:
                        async with AsyncSessionLocal() as session:
                            await RequestRepository.update_status(session, db_request_id, 'ERROR')

                context.user_data.clear()
                break

            elif status == 'failed':
                await _safe_edit_or_reply(
                    processing_msg, update,
                    "❌ Анализ завершился с ошибкой на сервере.",
                    reply_markup=get_error_keyboard()
                )
                context.user_data.clear()
                break

            if attempt >= max_attempts:
                await _safe_edit_or_reply(
                    processing_msg, update,
                    "⏱️ Время ожидания истекло.",
                    reply_markup=get_error_keyboard()
                )
                if db_request_id:
                    async with AsyncSessionLocal() as session:
                        await RequestRepository.update_status(session, db_request_id, 'ERROR')
                context.user_data.clear()
                break

    except Exception as e:
        logger.error(f"Error in monitor: {e}", exc_info=True)
    finally:
        await client.close()