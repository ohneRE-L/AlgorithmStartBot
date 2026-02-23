"""
Клиент для взаимодействия с сервером алгоритмов
"""
import aiohttp
import logging
from typing import Optional, Tuple
from config import ALGORITHM_SERVER_URL
import os

logger = logging.getLogger(__name__)


class AlgorithmServerClient:
    def __init__(self, base_url: str = ALGORITHM_SERVER_URL):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def start_analysis(self, algorithm_id: str, file_path: str, user_id: int) -> Tuple[
        bool, Optional[str], Optional[str]]:
        """Отправляет файл на сервер для начала анализа"""
        try:
            session = await self._get_session()

            data = aiohttp.FormData()
            data.add_field('algorithm_id', algorithm_id)
            data.add_field('user_id', str(user_id))
            data.add_field('file', open(file_path, 'rb'), filename=os.path.basename(file_path))

            async with session.post(f"{self.base_url}/api/start_analysis", data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return True, result.get('task_id'), None
                else:
                    error_text = await response.text()
                    return False, None, f"Сервер вернул ошибку {response.status}: {error_text}"
        except Exception as e:
            logger.error(f"Ошибка при связи с сервером алгоритмов: {e}")
            return False, None, str(e)

    async def check_status(self, task_id: str) -> Tuple[str, Optional[str]]:
        """Спрашивает сервер: 'Готово или нет?'"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/task/{task_id}/status") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('status'), None  # 'processing', 'completed', 'failed'
                return 'failed', f"Статус {response.status}"
        except Exception as e:
            return 'failed', str(e)

    async def get_result(self, task_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Скачивает готовый файл результата с сервера"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/task/{task_id}/result") as response:
                if response.status == 200:
                    os.makedirs('results', exist_ok=True)
                    result_path = f"results/{task_id}_final_output.png"
                    with open(result_path, 'wb') as f:
                        f.write(await response.read())
                    return True, result_path, None
                return False, None, "Не удалось скачать файл"
        except Exception as e:
            return False, None, str(e)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

