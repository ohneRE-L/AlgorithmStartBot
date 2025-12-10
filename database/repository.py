import logging
import os
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import User, Region, SourceImage, AnalysisRequest, Result

logger = logging.getLogger(__name__)


class UserRepository:
    @staticmethod
    async def get_or_create_user(
            session: AsyncSession,
            telegram_id: int,
            username: Optional[str] = None
    ) -> User:
        try:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user:
                if username and user.username != username:
                    user.username = username
                    await session.commit()
                return user

            user = User(
                telegram_id=telegram_id,
                username=username,
                role='OPERATOR'
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Created new user: {telegram_id} ({username})")
            return user
        except Exception as e:
            await session.rollback()
            logger.error(f"Error in get_or_create_user: {e}", exc_info=True)
            raise


class RequestRepository:
    @staticmethod
    async def create_analysis_request(
            session: AsyncSession,
            user_id: int,
            file_path: str,
            file_size: int,
            algorithm_name: str
    ) -> AnalysisRequest:
        try:
            # 1. Создаем запись о файле
            ext = os.path.splitext(file_path)[1].lower() if file_path else None
            source_image = SourceImage(
                file_path=file_path,
                file_size=file_size,
                file_extension=ext
            )
            session.add(source_image)
            await session.flush()  # Получаем ID картинки

            # 2. Пытаемся найти дефолтный регион (опционально)
            # В реальном проекте здесь был бы выбор региона пользователем
            region_res = await session.execute(select(Region).limit(1))
            region = region_res.scalar_one_or_none()
            region_id = region.id if region else None

            # 3. Создаем заявку
            request = AnalysisRequest(
                user_id=user_id,
                source_image_id=source_image.id,
                region_id=region_id,
                algorithm_name=algorithm_name,
                status='PENDING'
            )
            session.add(request)
            await session.commit()
            await session.refresh(request)

            logger.info(f"Created analysis request: {request.id} for user {user_id}")
            return request
        except Exception as e:
            await session.rollback()
            logger.error(f"Error in create_analysis_request: {e}", exc_info=True)
            raise

    @staticmethod
    async def update_status(
            session: AsyncSession,
            request_id: str,
            status: str
    ) -> bool:
        try:
            valid_statuses = ('PENDING', 'PROCESSING', 'COMPLETED', 'ERROR')
            if status not in valid_statuses:
                logger.error(f"Invalid status: {status}")
                return False

            await session.execute(
                update(AnalysisRequest)
                .where(AnalysisRequest.id == request_id)
                .values(status=status)
            )
            await session.commit()
            logger.info(f"Updated request {request_id} status to {status}")
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating status: {e}", exc_info=True)
            return False


class ResultRepository:
    @staticmethod
    async def create_result(
            session: AsyncSession,
            request_id: str,
            metadata: dict
    ) -> Result:
        try:
            result = Result(
                analysis_request_id=request_id,
                result_metadata=metadata
            )
            session.add(result)
            await session.commit()
            await session.refresh(result)
            logger.info(f"Created result for request {request_id}")
            return result
        except Exception as e:
            await session.rollback()
            logger.error(f"Error create_result: {e}", exc_info=True)
            raise