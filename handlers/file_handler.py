import os
import asyncio
import logging
from telegram import Update
from telegram.error import TelegramError, TimedOut, NetworkError
from telegram.ext import ContextTypes
from utils.file_validator import validate_file
from server_client import AlgorithmServerClient
from config import TELEGRAM_MAX_FILE_SIZE, USE_LOCAL_BOT_API
from handlers.command_handler import (
    get_error_keyboard,
    get_main_keyboard,
    get_after_result_keyboard,
    show_algorithms
)
from database.db_session import AsyncSessionLocal
# Импортируем обновленные репозитории
from database.repository import UserRepository, RequestRepository, ResultRepository

logger = logging.getLogger(__name__)


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text if update.message.text else ""
    if user_text == "🔙 Выбрать другой алгоритм" or user_text == "📋 Выбрать другой алгоритм":
        context.user_data['state'] = 'waiting_algorithm'
        await show_algorithms(update, context)
        return

    if user_text == "❌ Отмена":
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        return

    if context.user_data.get('state') != 'waiting_file':
        await update.message.reply_text(
            "❌ Сначала выберите алгоритм, используя кнопку 'Выбрать алгоритм'",
            reply_markup=get_main_keyboard()
        )
        return

    if 'selected_algorithm' not in context.user_data:
        await update.message.reply_text(
            "❌ Алгоритм не выбран. Используйте кнопку 'Выбрать алгоритм' для начала работы.",
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
        try:
            file_obj = await context.bot.get_file(file.file_id)
        except TelegramError as e:
            error_msg = str(e)
            logger.error(f"Error getting file: {error_msg}")
            error_text = f"❌ Ошибка при получении файла:\n{error_msg}\nПопробуйте загрузить файл снова."
            if processing_msg:
                try:
                    await processing_msg.edit_text(error_text, reply_markup=get_error_keyboard())
                except:
                    pass
            else:
                await update.message.reply_text(error_text, reply_markup=get_error_keyboard())
            context.user_data['state'] = 'waiting_file'
            return

        if is_photo:
            file_name = f"photo_{file.file_id}.jpg"
        else:
            file_name = getattr(file, 'file_name', None) or f"file_{file.file_id}"

        download_path = f"downloads/{update.effective_user.id}_{file_name}"
        os.makedirs('downloads', exist_ok=True)

        logger.info(f"Starting file download: {file_name}, size: {file_size} bytes")
        await file_obj.download_to_drive(download_path)

        # Получаем реальный размер файла после скачивания
        real_file_size = os.path.getsize(download_path)
        is_valid, error_message = validate_file(download_path, real_file_size)

        if not is_valid:
            error_text = f"❌ Ошибка проверки файла:\n{error_message}\n\nВыберите действие:"
            if processing_msg:
                try:
                    await processing_msg.edit_text(error_text, reply_markup=get_error_keyboard())
                except:
                    pass
            try:
                os.remove(download_path)
            except:
                pass
            context.user_data['state'] = 'waiting_file'
            return

        status_text = "✅ Файл проверен и готов к обработке.\n🚀 Запускаю анализ на сервере..."
        if processing_msg:
            try:
                await processing_msg.edit_text(status_text)
            except:
                pass

        # Работа с БД
        db_request = None
        user_id = update.effective_user.id
        algo_name = context.user_data['selected_algorithm']['name']

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
        algorithm_id = context.user_data['selected_algorithm']['id']
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
            monitor_task_status(update, context, server_task_id, download_path, request_id)
        )

    except Exception as e:
        logger.error(f"Unexpected error in handle_file: {e}", exc_info=True)
        if processing_msg:
            try:
                await processing_msg.edit_text("❌ Произошла непредвиденная ошибка.", reply_markup=get_error_keyboard())
            except:
                pass
        context.user_data['state'] = 'error'


async def monitor_task_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        server_task_id: str,
        file_path: str,
        db_request_id: str = None
):
    client = AlgorithmServerClient()
    max_attempts = 60
    attempt = 0
    try:
        while attempt < max_attempts:
            await asyncio.sleep(5)
            status, error = await client.check_status(server_task_id)
            attempt += 1

            # Маппинг статусов сервера на статусы БД
            # server: processing, completed, failed, queued
            # db: PENDING, PROCESSING, COMPLETED, ERROR
            if db_request_id and status:
                try:
                    async with AsyncSessionLocal() as session:
                        status_map = {
                            'processing': 'PROCESSING',
                            'completed': 'COMPLETED',
                            'failed': 'ERROR',
                            'queued': 'PENDING'
                        }
                        db_status = status_map.get(status, 'PROCESSING')
                        # Не обновляем статус каждый раз, если он не меняется, чтобы не спамить БД,
                        # но в MVP можно оставить простой update
                        await RequestRepository.update_status(
                            session=session,
                            request_id=db_request_id,
                            status=db_status
                        )
                except Exception as e:
                    logger.error(f"Error updating DB status: {e}")

            if error:
                try:
                    await update.message.reply_text(
                        f"❌ Ошибка при проверке статуса:\n{error}\n\nВыберите действие:",
                        reply_markup=get_error_keyboard()
                    )
                except:
                    pass
                if db_request_id:
                    async with AsyncSessionLocal() as session:
                        await RequestRepository.update_status(session, db_request_id, 'ERROR')
                context.user_data.clear()
                break

            if status == 'completed':
                await update.message.reply_text("✅ Анализ завершен! Получаю результат...")
                success, result_path, error = await client.get_result(server_task_id)

                if success:
                    # 1. Сохраняем результат в БД
                    if db_request_id:
                        try:
                            async with AsyncSessionLocal() as session:
                                await RequestRepository.update_status(session, db_request_id, 'COMPLETED')
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
                        except Exception as e:
                            logger.error(f"Error saving result to DB: {e}", exc_info=True)

                    # 2. Отправляем файл пользователю
                    try:
                        with open(result_path, 'rb') as result_file:
                            await update.message.reply_document(
                                document=result_file,
                                caption=f"📊 Результат анализа\nАлгоритм: {context.user_data.get('selected_algorithm', {}).get('name', 'N/A')}"
                            )
                        await update.message.reply_text("✅ Результат успешно отправлен!",
                                                        reply_markup=get_after_result_keyboard())

                        # Чистим файлы
                        try:
                            os.remove(file_path)
                            os.remove(result_path)
                        except:
                            pass

                    except Exception as e:
                        logger.error(f"Error sending file: {e}")
                        await update.message.reply_text("❌ Ошибка отправки файла.", reply_markup=get_error_keyboard())
                else:
                    await update.message.reply_text(f"❌ Не удалось скачать результат: {error}",
                                                    reply_markup=get_error_keyboard())
                    if db_request_id:
                        async with AsyncSessionLocal() as session:
                            await RequestRepository.update_status(session, db_request_id, 'ERROR')

                context.user_data.clear()
                break

            elif status == 'failed':
                await update.message.reply_text("❌ Анализ завершился с ошибкой на сервере.",
                                                reply_markup=get_error_keyboard())
                context.user_data.clear()
                break

            if attempt >= max_attempts:
                await update.message.reply_text("⏱️ Время ожидания истекло.", reply_markup=get_error_keyboard())
                if db_request_id:
                    async with AsyncSessionLocal() as session:
                        await RequestRepository.update_status(session, db_request_id, 'ERROR')
                context.user_data.clear()
                break

    except Exception as e:
        logger.error(f"Error in monitor: {e}", exc_info=True)
    finally:
        await client.close()