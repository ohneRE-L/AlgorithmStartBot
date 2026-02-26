"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из token.env или .env
load_dotenv('token.env')  # Сначала пробуем token.env
load_dotenv('.env')  # Затем .env (если token.env не найден, это не вызовет ошибку)

# Токен Telegram бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# Telegram Application API (создаётся на my.telegram.org) — нужны для локального Bot API
# Локальный сервер позволяет загружать файлы до 2000 МБ вместо 20 МБ
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID', '')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')

# URL локального сервера Bot API (если используется)
# При использовании задайте в token.env и запустите локальный сервер (см. run_local_bot_api.py)
# Пример: 'http://localhost:8081'
LOCAL_BOT_API_URL = os.getenv('LOCAL_BOT_API_URL', '')

# URL сервера алгоритмов
ALGORITHM_SERVER_URL = os.getenv('ALGORITHM_SERVER_URL', 'http://localhost:8000')

# Поддерживаемые форматы файлов
SUPPORTED_FILE_FORMATS = ['.tif', '.tiff', '.geotiff', '.jpg', '.jpeg', '.png']

# Максимальный размер файла для валидации (в байтах)
# Если используется локальный сервер Bot API, можно установить до 2000 МБ
# Если используется официальный API, лимит - 20 МБ
USE_LOCAL_BOT_API = bool(LOCAL_BOT_API_URL)

if USE_LOCAL_BOT_API:
    # Локальный Bot API (api_id/api_hash): макс. размер по документации Telegram — 2000 МБ
    MAX_FILE_SIZE = 2000 * 1024 * 1024
    TELEGRAM_MAX_FILE_SIZE = 2000 * 1024 * 1024
else:
    # Без локального сервера лимит - 20 МБ
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 МБ для валидации
    TELEGRAM_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ для скачивания

# Таймауты для скачивания файлов (секунды). Для больших файлов через локальный API — больше
FILE_DOWNLOAD_READ_TIMEOUT = 600 if USE_LOCAL_BOT_API else 30
FILE_DOWNLOAD_WRITE_TIMEOUT = 600 if USE_LOCAL_BOT_API else 30
FILE_DOWNLOAD_CONNECT_TIMEOUT = 30

# Доступные алгоритмы (один алгоритм OEM-Lightweight)
AVAILABLE_ALGORITHMS = {
    '1': {
        'id': 'agriculture_classification',
        'name': 'Классификация земель OEM-Lightweight',
        'description': 'Сегментация земель по данным аэрофотосъёмки с помощью модели OEM-Lightweight'
    }
}

