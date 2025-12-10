"""
Настройка подключения к базе данных и сессий
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv('token.env')
load_dotenv('.env')

logger = logging.getLogger(__name__)

# Получаем параметры подключения из переменных окружения
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', 'postgres')
DB_NAME = os.getenv('DB_NAME', 'agro_bot_db')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')

# Исправляем localhost на 127.0.0.1 для Windows (может решить проблемы с подключением)
if DB_HOST == 'localhost':
    DB_HOST = '127.0.0.1'

# URL-кодируем пароль на случай специальных символов
from urllib.parse import quote_plus
DB_PASS_ENCODED = quote_plus(DB_PASS)

# Формируем URL подключения
# Используем asyncpg для async подключения к PostgreSQL
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS_ENCODED}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Логируем параметры подключения (без пароля)
logger.info(f"Подключение к БД: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
logger.debug(f"URL подключения (без пароля): postgresql+asyncpg://{DB_USER}:***@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# Создаем движок с дополнительными параметрами для стабильности подключения
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Установите True для отладки SQL запросов
    future=True,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600  # Переподключение каждые 3600 секунд
)

# Создаем фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db_session():
    """
    Получить сессию базы данных (для использования в dependency injection)
    Генератор для использования с async context manager
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Инициализация базы данных - создание всех таблиц
    """
    try:
        from database.models import Base
        from sqlalchemy import text
        logger.info("Попытка подключения к БД...")
        # Проверяем подключение перед созданием таблиц
        async with engine.connect() as conn:
            logger.info("Подключение установлено успешно!")
            # Проверяем, существуют ли уже таблицы
            result = await conn.execute(
                text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')")
            )
            tables_exist = result.scalar()
            if tables_exist:
                logger.info("Таблицы уже существуют")
            else:
                logger.info("Создаю таблицы...")
                async with engine.begin() as trans_conn:
                    await trans_conn.run_sync(Base.metadata.create_all)
                    logger.info("Таблицы созданы успешно")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}", exc_info=True)
        logger.error(f"Проверьте пароль в token.env и убедитесь, что PostgreSQL принимает TCP/IP подключения")
        raise


async def close_db():
    """
    Закрытие соединения с базой данных
    """
    await engine.dispose()

