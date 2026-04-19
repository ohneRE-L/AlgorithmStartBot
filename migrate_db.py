import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

# Загружаем переменные из env
load_dotenv("token.env")

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME", "agro_bot_db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def migrate():
    print(f"Connecting to {DB_NAME}...")
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        print("Updating CHECK constraints...")
        
        # 1. Обновляем статус для заявок
        try:
            # Сначала удаляем старое ограничение
            await conn.execute(text("ALTER TABLE analysis_requests DROP CONSTRAINT IF EXISTS check_request_status;"))
            # Добавляем новое
            await conn.execute(text(
                "ALTER TABLE analysis_requests ADD CONSTRAINT check_request_status "
                "CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'ERROR', 'PENDING_MODERATION', 'REJECTED', 'CANCELLED'));"
            ))
            print("✅ check_request_status updated successfully.")
        except Exception as e:
            print(f"❌ Error updating check_request_status: {e}")

        # 2. Обновляем роли (на случай если там старое ограничение)
        try:
            await conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS check_user_role;"))
            await conn.execute(text(
                "ALTER TABLE users ADD CONSTRAINT check_user_role "
                "CHECK (role IN ('OPERATOR', 'MODERATOR'));"
            ))
            print("✅ check_user_role updated successfully.")
        except Exception as e:
            print(f"❌ Error updating check_user_role: {e}")

    await engine.dispose()
    print("\nMigration finished. You can now restart the bot.")

if __name__ == "__main__":
    asyncio.run(migrate())
