"""
Утилиты для проверки файлов
"""
import os
from typing import Tuple, Optional
from config import SUPPORTED_FILE_FORMATS, MAX_FILE_SIZE


def validate_file(file_path: str, file_size: int) -> Tuple[bool, Optional[str]]:
    """
    Проверяет корректность загруженного файла
    
    Args:
        file_path: Путь к файлу
        file_size: Размер файла в байтах
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден ли файл, сообщение об ошибке если есть)
    """
    # Проверка размера файла
    if file_size > MAX_FILE_SIZE:
        return False, f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE / (1024*1024):.0f} МБ"
    
    # Проверка расширения файла
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext not in SUPPORTED_FILE_FORMATS:
        return False, f"Неподдерживаемый формат файла. Поддерживаемые форматы: {', '.join(SUPPORTED_FILE_FORMATS)}"
    
    # Проверка существования файла
    if not os.path.exists(file_path):
        return False, "Файл не найден"
    
    # Дополнительная проверка целостности (базовая)
    try:
        # Для изображений можно проверить через Pillow
        if file_ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff']:
            from PIL import Image
            # Для аэрофото/ортоснимков лимит пикселей Pillow по умолчанию (~179 Мп) мал — временно повышаем
            old_max = getattr(Image, 'MAX_IMAGE_PIXELS', None)
            try:
                Image.MAX_IMAGE_PIXELS = 2_000_000_000  # 2 Гпкс, достаточно для больших орто
                img = Image.open(file_path)
                img.verify()
            except Exception as e:
                return False, f"Файл поврежден или имеет некорректный формат: {str(e)}"
            finally:
                if old_max is not None:
                    Image.MAX_IMAGE_PIXELS = old_max
    except ImportError:
        # Если Pillow не установлен, пропускаем проверку
        pass
    
    return True, None

