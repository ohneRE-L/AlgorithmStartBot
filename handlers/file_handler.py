"""
Обработчики загрузки и обработки файлов
"""
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
from handlers.algorithm_handler import get_file_upload_keyboard

logger = logging.getLogger(__name__)


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает загруженный файл"""
    user_text = update.message.text if update.message.text else ""
    
    # Обработка кнопок при ожидании файла
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
    
    # Проверяем, что пользователь в правильном состоянии
    if context.user_data.get('state') != 'waiting_file':
        await update.message.reply_text(
            "❌ Сначала выберите алгоритм, используя кнопку 'Выбрать алгоритм'",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Проверяем наличие выбранного алгоритма
    if 'selected_algorithm' not in context.user_data:
        await update.message.reply_text(
            "❌ Алгоритм не выбран. Используйте кнопку 'Выбрать алгоритм' для начала работы.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Получаем файл
    is_photo = False
    if update.message.document:
        file = update.message.document
    elif update.message.photo:
        # Если отправлено фото, берем самое большое
        file = update.message.photo[-1]
        is_photo = True
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте файл как документ или фото."
        )
        return
    
    # Проверяем размер файла (лимит зависит от использования локального сервера Bot API)
    file_size = getattr(file, 'file_size', None)
    
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
    
    # Отправляем сообщение о начале обработки с повторными попытками
    processing_msg = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            processing_msg = await update.message.reply_text(
                "⏳ Проверяю файл..."
            )
            break  # Успешно отправили
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Failed to send processing message (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                # Ждем перед повторной попыткой
                await asyncio.sleep(1)
            # Если все попытки исчерпаны, продолжаем без сообщения
    
    # Скачиваем файл
    try:
        try:
            file_obj = await context.bot.get_file(file.file_id)
        except TelegramError as e:
            error_msg = str(e)
            logger.error(f"Error getting file: {error_msg}")
            
            # Специальная обработка для больших файлов
            if "too big" in error_msg.lower() or "file is too big" in error_msg.lower():
                max_size_mb = int(TELEGRAM_MAX_FILE_SIZE / (1024 * 1024))
                api_info = "локального сервера Bot API" if USE_LOCAL_BOT_API else "Telegram Bot API"
                error_text = (
                    f"❌ Файл слишком большой для скачивания через {api_info}.\n\n"
                    f"Максимальный размер файла для скачивания: {max_size_mb} МБ\n\n"
                    "Пожалуйста, загрузите файл меньшего размера или используйте сжатие."
                )
            else:
                error_text = (
                    f"❌ Ошибка при получении файла:\n{error_msg}\n\n"
                    "Возможно, файл уже недоступен.\n"
                    "Попробуйте загрузить файл снова."
                )
            
            if processing_msg:
                try:
                    await processing_msg.edit_text(
                        error_text,
                        reply_markup=get_error_keyboard()
                    )
                except:
                    pass
            else:
                try:
                    await update.message.reply_text(
                        error_text,
                        reply_markup=get_error_keyboard()
                    )
                except:
                    pass
            context.user_data['state'] = 'waiting_file'
            return
        
        # Определяем имя файла
        if is_photo:
            # Для фото используем file_id с расширением .jpg
            file_name = f"photo_{file.file_id}.jpg"
        else:
            # Для документов используем оригинальное имя или генерируем
            file_name = getattr(file, 'file_name', None) or f"file_{file.file_id}"
        
        download_path = f"downloads/{update.effective_user.id}_{file_name}"
        
        # Создаем директорию для загрузок
        os.makedirs('downloads', exist_ok=True)
        
        # Скачиваем файл с обработкой ошибок
        file_size_info = getattr(file, 'file_size', 'unknown')
        logger.info(f"Starting file download: {file_name}, size: {file_size_info} bytes")
        try:
            await file_obj.download_to_drive(download_path)
            logger.info(f"File downloaded successfully: {download_path}")
        except (TimedOut, NetworkError) as e:
            logger.error(f"Network error while downloading file: {e}")
            if processing_msg:
                try:
                    await processing_msg.edit_text(
                        "❌ Ошибка сети при загрузке файла.\n"
                        "Попробуйте загрузить файл снова.",
                        reply_markup=get_error_keyboard()
                    )
                except:
                    pass
            context.user_data['state'] = 'waiting_file'
            return
        
        # Если не удалось отправить начальное сообщение, отправляем его сейчас
        if not processing_msg:
            try:
                processing_msg = await update.message.reply_text(
                    "✅ Файл загружен. Проверяю..."
                )
            except:
                pass  # Продолжаем работу даже если не удалось отправить
        
        # Проверяем файл
        file_size = os.path.getsize(download_path)
        logger.info(f"Validating file: {download_path}, size: {file_size} bytes")
        is_valid, error_message = validate_file(download_path, file_size)
        
        if not is_valid:
            error_text = (
                f"❌ Ошибка проверки файла:\n{error_message}\n\n"
                "Выберите действие:"
            )
            if processing_msg:
                try:
                    await processing_msg.edit_text(
                        error_text,
                        reply_markup=get_error_keyboard()
                    )
                except:
                    try:
                        await update.message.reply_text(
                            error_text,
                            reply_markup=get_error_keyboard()
                        )
                    except:
                        pass
            else:
                try:
                    await update.message.reply_text(
                        error_text,
                        reply_markup=get_error_keyboard()
                    )
                except:
                    pass
            # Удаляем некорректный файл
            try:
                os.remove(download_path)
            except:
                pass
            # Сбрасываем состояние, чтобы можно было повторить
            context.user_data['state'] = 'waiting_file'
            return
        
        # Файл валиден, переходим к отправке на сервер
        status_text = (
            "✅ Файл проверен и готов к обработке.\n"
            "🚀 Запускаю анализ на сервере..."
        )
        if processing_msg:
            try:
                await processing_msg.edit_text(status_text)
            except:
                # Если не удалось отредактировать, отправляем новое сообщение
                try:
                    processing_msg = await update.message.reply_text(status_text)
                except:
                    pass
        else:
            try:
                processing_msg = await update.message.reply_text(status_text)
            except:
                pass
        
        # Запускаем анализ
        client = AlgorithmServerClient()
        algorithm_id = context.user_data['selected_algorithm']['id']
        user_id = update.effective_user.id
        
        success, task_id, error = await client.start_analysis(
            algorithm_id,
            download_path,
            user_id
        )
        
        if not success:
            error_text = (
                f"❌ Ошибка при запуске анализа:\n{error}\n\n"
                "Выберите действие:"
            )
            if processing_msg:
                try:
                    await processing_msg.edit_text(
                        error_text,
                        reply_markup=get_error_keyboard()
                    )
                except:
                    try:
                        await update.message.reply_text(
                            error_text,
                            reply_markup=get_error_keyboard()
                        )
                    except:
                        pass
            else:
                try:
                    await update.message.reply_text(
                        error_text,
                        reply_markup=get_error_keyboard()
                    )
                except:
                    pass
            await client.close()
            context.user_data['state'] = 'error'
            return
        
        # Сохраняем информацию о задаче
        context.user_data['task_id'] = task_id
        context.user_data['file_path'] = download_path
        context.user_data['state'] = 'processing'
        
        success_text = (
            f"✅ Анализ запущен!\n"
            f"📋 ID задачи: {task_id}\n\n"
            f"⏳ Ожидаю завершения анализа..."
        )
        if processing_msg:
            try:
                await processing_msg.edit_text(success_text)
            except:
                try:
                    processing_msg = await update.message.reply_text(success_text)
                except:
                    pass
        else:
            try:
                processing_msg = await update.message.reply_text(success_text)
            except:
                pass
        
        await client.close()
        
        # Запускаем мониторинг статуса задачи
        asyncio.create_task(
            monitor_task_status(update, context, task_id, download_path)
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in handle_file: {e}", exc_info=True)
        error_text = (
            f"❌ Произошла ошибка при обработке файла:\n{str(e)}\n\n"
            "Попробуйте еще раз или используйте кнопки для навигации."
        )
        if processing_msg:
            try:
                await processing_msg.edit_text(
                    error_text,
                    reply_markup=get_error_keyboard()
                )
            except:
                try:
                    await update.message.reply_text(
                        error_text,
                        reply_markup=get_error_keyboard()
                    )
                except:
                    pass
        else:
            try:
                await update.message.reply_text(
                    error_text,
                    reply_markup=get_error_keyboard()
                )
            except:
                pass
        context.user_data['state'] = 'error'


async def monitor_task_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_id: str,
    file_path: str
):
    """Мониторит статус выполнения задачи"""
    client = AlgorithmServerClient()
    max_attempts = 60  # Максимум 60 проверок
    attempt = 0
    
    try:
        while attempt < max_attempts:
            await asyncio.sleep(5)  # Проверяем каждые 5 секунд
            
            status, error = await client.check_status(task_id)
            
            if error:
                try:
                    await update.message.reply_text(
                        f"❌ Ошибка при проверке статуса:\n{error}\n\n"
                        "Выберите действие:",
                        reply_markup=get_error_keyboard()
                    )
                except (TimedOut, NetworkError) as e:
                    logger.warning(f"Failed to send error message: {e}")
                context.user_data.clear()
                break
            
            if status == 'completed':
                # Получаем результат
                try:
                    await update.message.reply_text(
                        "✅ Анализ завершен! Получаю результат..."
                    )
                except (TimedOut, NetworkError) as e:
                    logger.warning(f"Failed to send completion message: {e}")
                
                success, result_path, error = await client.get_result(task_id)
                
                if success:
                    # Отправляем результат пользователю
                    try:
                        with open(result_path, 'rb') as result_file:
                            try:
                                await update.message.reply_document(
                                    document=result_file,
                                    caption=f"📊 Результат анализа\nАлгоритм: {context.user_data.get('selected_algorithm', {}).get('name', 'Неизвестно')}"
                                )
                            except (TimedOut, NetworkError) as e:
                                logger.warning(f"Failed to send document: {e}")
                                try:
                                    await update.message.reply_text(
                                        "⚠️ Не удалось отправить файл из-за проблем с сетью.\n"
                                        "Попробуйте запросить результат позже."
                                    )
                                except:
                                    pass
                                # Не очищаем файлы, чтобы можно было попробовать позже
                                context.user_data.clear()
                                break
                        
                        try:
                            await update.message.reply_text(
                                "✅ Результат успешно отправлен!",
                                reply_markup=get_after_result_keyboard()
                            )
                        except (TimedOut, NetworkError) as e:
                            logger.warning(f"Failed to send success message: {e}")
                            # Пытаемся отправить без клавиатуры
                            try:
                                await update.message.reply_text(
                                    "✅ Результат успешно отправлен!"
                                )
                            except:
                                pass
                        
                        # Очищаем временные файлы
                        try:
                            os.remove(file_path)
                            os.remove(result_path)
                        except:
                            pass
                        
                    except Exception as e:
                        logger.error(f"Error sending result: {e}", exc_info=True)
                        try:
                            await update.message.reply_text(
                                f"❌ Ошибка при отправке результата:\n{str(e)}\n\n"
                                "Попробуйте запросить результат позже.",
                                reply_markup=get_error_keyboard()
                            )
                        except:
                            pass
                else:
                    try:
                        await update.message.reply_text(
                            f"❌ Ошибка при получении результата:\n{error}\n\n"
                            "Выберите действие:",
                            reply_markup=get_error_keyboard()
                        )
                    except (TimedOut, NetworkError) as e:
                        logger.warning(f"Failed to send error message: {e}")
                
                context.user_data.clear()
                break
            
            elif status == 'failed':
                try:
                    await update.message.reply_text(
                        "❌ Анализ завершился с ошибкой.\n\n"
                        "Выберите действие:",
                        reply_markup=get_error_keyboard()
                    )
                except (TimedOut, NetworkError) as e:
                    logger.warning(f"Failed to send error message: {e}")
                context.user_data.clear()
                break
            
            attempt += 1
        
        if attempt >= max_attempts:
            try:
                await update.message.reply_text(
                    "⏱️ Превышено время ожидания результата.\n\n"
                    "Выберите действие:",
                    reply_markup=get_error_keyboard()
                )
            except (TimedOut, NetworkError) as e:
                logger.warning(f"Failed to send timeout message: {e}")
            context.user_data.clear()
    
    except Exception as e:
        logger.error(f"Error in monitor_task_status: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                f"❌ Произошла ошибка при мониторинге задачи:\n{str(e)}\n\n"
                "Используйте /start для начала заново.",
                reply_markup=get_error_keyboard()
            )
        except:
            pass
        context.user_data.clear()
    
    finally:
        await client.close()

