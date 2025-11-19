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

# URL локального сервера Bot API (если используется)
# Если установлен, бот будет использовать локальный сервер вместо официального API
# Это позволяет загружать файлы до 2000 МБ вместо 20 МБ
# Пример: 'http://localhost:8081' (по умолчанию порт 8081)
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
    # С локальным сервером Bot API можно загружать до 2000 МБ
    MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2000 МБ
    TELEGRAM_MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2000 МБ
else:
    # Без локального сервера лимит - 20 МБ
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 МБ для валидации
    TELEGRAM_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ для скачивания

# Доступные алгоритмы
AVAILABLE_ALGORITHMS = {
    '1': {
        'id': 'agriculture_classification',
        'name': 'Классификация сельскохозяйственных земель',
        'description': 'Автоматическая классификация типов сельскохозяйственных угодий'
    },
    '2': {
        'id': 'vegetation_index',
        'name': 'Расчет вегетационных индексов',
        'description': 'NDVI, EVI и другие индексы растительности'
    },
    '3': {
        'id': 'object_detection',
        'name': 'Детекция объектов',
        'description': 'Обнаружение и классификация объектов на снимках'
    },
    '4': {
        'id': 'change_detection',
        'name': 'Детекция изменений',
        'description': 'Выявление изменений между снимками разных периодов'
    }
}

