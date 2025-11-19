"""
Клиент для взаимодействия с сервером алгоритмов
"""
import aiohttp
import asyncio
import time
import logging
from typing import Dict, Optional, Tuple
from config import ALGORITHM_SERVER_URL

logger = logging.getLogger(__name__)

# Хранилище для отслеживания задач (в прототипе)
# В реальной реализации это будет база данных на сервере
_task_times: Dict[str, float] = {}


class AlgorithmServerClient:
    """Клиент для работы с сервером алгоритмов"""
    
    def __init__(self, base_url: str = ALGORITHM_SERVER_URL):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        # Время обработки задачи в секундах (для прототипа)
        self.processing_time = 30  # 30 секунд для демонстрации
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получает или создает сессию aiohttp"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def start_analysis(
        self, 
        algorithm_id: str, 
        file_path: str,
        user_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Запускает анализ на сервере алгоритмов
        
        Args:
            algorithm_id: ID выбранного алгоритма
            file_path: Путь к файлу с данными
            user_id: ID пользователя Telegram
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: 
            (успешно ли запущен, task_id если успешно, сообщение об ошибке если нет)
        """
        try:
            session = await self._get_session()
            
            # В реальной реализации здесь будет отправка файла на сервер
            # Для прототипа симулируем успешный запуск
            await asyncio.sleep(0.5)  # Имитация сетевой задержки
            
            # Генерируем фиктивный task_id
            current_time = time.time()
            task_id = f"task_{user_id}_{algorithm_id}_{current_time}"
            
            # Сохраняем время создания задачи для симуляции
            _task_times[task_id] = current_time
            
            # В реальной реализации:
            # with open(file_path, 'rb') as f:
            #     form_data = aiohttp.FormData()
            #     form_data.add_field('file', f, filename=os.path.basename(file_path))
            #     form_data.add_field('algorithm_id', algorithm_id)
            #     form_data.add_field('user_id', str(user_id))
            #     
            #     async with session.post(
            #         f"{self.base_url}/api/start_analysis",
            #         data=form_data
            #     ) as response:
            #         if response.status == 200:
            #             data = await response.json()
            #             return True, data.get('task_id'), None
            #         else:
            #             error = await response.text()
            #             return False, None, error
            
            return True, task_id, None
            
        except Exception as e:
            return False, None, f"Ошибка при запуске анализа: {str(e)}"
    
    async def check_status(self, task_id: str) -> Tuple[str, Optional[str]]:
        """
        Проверяет статус выполнения задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Tuple[str, Optional[str]]: (статус, сообщение об ошибке если есть)
            Статусы: 'pending', 'processing', 'completed', 'failed'
        """
        try:
            session = await self._get_session()
            
            # В реальной реализации:
            # async with session.get(f"{self.base_url}/api/task/{task_id}/status") as response:
            #     if response.status == 200:
            #         data = await response.json()
            #         return data.get('status'), None
            #     else:
            #         return 'failed', f"Ошибка при проверке статуса: {response.status}"
            
            # Для прототипа симулируем проверку статуса
            await asyncio.sleep(0.2)
            
            # Проверяем, прошло ли достаточно времени для завершения задачи
            if task_id in _task_times:
                elapsed_time = time.time() - _task_times[task_id]
                remaining_time = max(0, self.processing_time - elapsed_time)
                
                if elapsed_time >= self.processing_time:
                    # Задача завершена
                    logger.info(f"Task {task_id} completed after {elapsed_time:.1f} seconds")
                    # Удаляем задачу из словаря после завершения
                    _task_times.pop(task_id, None)
                    return 'completed', None
                else:
                    # Задача еще обрабатывается
                    logger.debug(f"Task {task_id} processing... {remaining_time:.1f}s remaining")
                    return 'processing', None
            else:
                # Задача не найдена (не должна происходить в прототипе)
                logger.warning(f"Task {task_id} not found in tracking dictionary")
                return 'failed', "Задача не найдена"
            
        except Exception as e:
            return 'failed', f"Ошибка при проверке статуса: {str(e)}"
    
    async def get_result(self, task_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Получает результат выполнения задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: 
            (успешно ли получен результат, путь к файлу результата, сообщение об ошибке)
        """
        try:
            session = await self._get_session()
            
            # В реальной реализации:
            # async with session.get(f"{self.base_url}/api/task/{task_id}/result") as response:
            #     if response.status == 200:
            #         # Сохраняем файл результата
            #         result_path = f"results/{task_id}_result.zip"
            #         with open(result_path, 'wb') as f:
            #             async for chunk in response.content.iter_chunked(8192):
            #                 f.write(chunk)
            #         return True, result_path, None
            #     else:
            #         error = await response.text()
            #         return False, None, error
            
            # Для прототипа создаем фиктивный файл результата
            import os
            from datetime import datetime
            os.makedirs('results', exist_ok=True)
            result_path = f"results/{task_id}_result.txt"
            
            # Извлекаем информацию об алгоритме из task_id
            algorithm_id = task_id.split('_')[2] if '_' in task_id else 'unknown'
            algorithm_names = {
                'agriculture': 'Классификация сельскохозяйственных земель',
                'vegetation': 'Расчет вегетационных индексов',
                'object': 'Детекция объектов',
                'change': 'Детекция изменений'
            }
            algo_name = next((name for key, name in algorithm_names.items() if key in algorithm_id), 'Неизвестный алгоритм')
            
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("РЕЗУЛЬТАТЫ АНАЛИЗА АЭРОФОТОСНИМКОВ\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"ID задачи: {task_id}\n")
                f.write(f"Алгоритм: {algo_name}\n\n")
                f.write("-" * 60 + "\n")
                f.write("СТАТИСТИКА ОБРАБОТКИ:\n")
                f.write("-" * 60 + "\n")
                f.write("Обработано пикселей: 12,450,000\n")
                f.write("Размер обработанной области: 5000 x 2490 пикселей\n")
                f.write("Время обработки: ~30 секунд\n\n")
                f.write("-" * 60 + "\n")
                f.write("РЕЗУЛЬТАТЫ:\n")
                f.write("-" * 60 + "\n")
                f.write("✓ Анализ успешно завершен\n")
                f.write("✓ Результаты сохранены\n")
                f.write("✓ Данные готовы к использованию\n\n")
                f.write("=" * 60 + "\n")
                f.write("ПРИМЕЧАНИЕ: Это прототип.\n")
                f.write("В реальной версии здесь будет файл с результатами анализа\n")
                f.write("(например, GeoTIFF с классификацией, JSON с метаданными и т.д.)\n")
                f.write("=" * 60 + "\n")
            
            return True, result_path, None
            
        except Exception as e:
            return False, None, f"Ошибка при получении результата: {str(e)}"
    
    async def close(self):
        """Закрывает сессию"""
        if self.session and not self.session.closed:
            await self.session.close()

