# Установите: pip install fastapi uvicorn python-multipart
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
import uuid
import os
import shutil

import sys
from pathlib import Path

# Пути к OEM-Lightweight и его подпакетам
OEM_ROOT = Path(__file__).parent / "oem-lightweight"
FASTERSEG_ROOT = OEM_ROOT / "fasterseg_api"
SPARSEMASK_ROOT = OEM_ROOT / "sparsemask_api"
OEM_PKG_ROOT = OEM_ROOT / "oem_lightweight"

# Добавляем их в sys.path, чтобы работали импорты OEM-кода
sys.path.insert(0, str(OEM_ROOT))
sys.path.insert(0, str(FASTERSEG_ROOT))
sys.path.insert(0, str(SPARSEMASK_ROOT))
sys.path.insert(0, str(OEM_PKG_ROOT))

from config import config  # это config из oem-lightweight (внутри OEM_ROOT)
from oem_lightweight.model import sparsemask, fasterseg
from oem_lightweight.evaluator import SegEvaluator
from oem_lightweight.utils import show_prediction, _open_image
import cv2
import numpy as np


app = FastAPI()

# Имитация базы данных задач
tasks = {}


# Глобальный кэш моделей, чтобы не грузить их каждый раз
_sparse_model = None
_fasterseg_model = None


def get_sparse_model():
    global _sparse_model
    if _sparse_model is None:
        arch_path = OEM_ROOT / "models" / "SparseMask" / "mask_thres_0.001.npy"
        weights_path = OEM_ROOT / "models" / "SparseMask" / "checkpoint_63750.pth.tar"
        if not arch_path.exists() or not weights_path.exists():
            raise FileNotFoundError(
                f"Не найдены файлы модели SparseMask:\n"
                f"  arch: {arch_path}\n"
                f"  weights: {weights_path}\n"
                f"Скачай их по ссылкам из README и положи в эти пути."
            )
        _sparse_model = sparsemask(mask=str(arch_path), weights=str(weights_path))
    return _sparse_model


def get_fasterseg_model():
    global _fasterseg_model
    if _fasterseg_model is None:
        arch_path = OEM_ROOT / "models" / "FasterSeg" / "arch_1.pt"
        weights_path = OEM_ROOT / "models" / "FasterSeg" / "weights1.pt"
        if not arch_path.exists() or not weights_path.exists():
            raise FileNotFoundError(
                f"Не найдены файлы модели FasterSeg:\n"
                f"  arch: {arch_path}\n"
                f"  weights: {weights_path}\n"
                f"Скачай их по ссылкам из README и положи в эти пути."
            )
        _fasterseg_model = fasterseg(arch=str(arch_path), weights=str(weights_path))
    return _fasterseg_model


def run_real_algorithm(task_id: str, input_path: str, algo_type: str):
    """
    Здесь вызываем OEM‑модель и сохраняем картинку‑результат.
    """
    try:
        print(f"Запуск алгоритма {algo_type} для задачи {task_id}...")

        # 1. Выбираем и загружаем модель (один раз, потом из кэша)
        # Связка с ID из config.AVAILABLE_ALGORITHMS бота:
        #   'agriculture_classification' -> SparseMask
        #   'object_detection'           -> FasterSeg
        if algo_type == "object_detection":
            network = get_fasterseg_model()  # dict(model=..., name="FasterSeg")
        else:
            # По умолчанию и для 'agriculture_classification' используем SparseMask
            network = get_sparse_model()  # dict(model=..., name="SparseMask")

        # 2. Читаем входное изображение так же, как в OEM-скрипте (через _open_image)
        img = _open_image(input_path)
        if img is None:
            raise RuntimeError(f"Не удалось прочитать входной файл: {input_path}")

        # 3. Готовим "data" для SegEvaluator
        h, w, _ = img.shape
        dummy_label = np.zeros((h, w), dtype=np.uint8)  # метки нам не нужны, но класс ждёт поле label
        data = {
            "img": img,
            "label": dummy_label,
            "filename": f"{task_id}"
        }

        # 4. Запускаем инференс
        evaluator = SegEvaluator(config, data, network)
        pred = evaluator.evaluate()  # pred: HxW, классы 0..7

        # 5. Красим предсказание в цвета
        colored = show_prediction(config.class_colors, -1, img, pred)

        # 6. Считаем проценты по классам и рисуем таблицу на изображении
        flat = pred.reshape(-1)
        counts = np.bincount(flat, minlength=config.num_classes)
        total = int(counts.sum()) or 1
        percents = counts.astype(np.float32) * 100.0 / float(total)

        lines = []
        stats = []
        for idx, (name, p) in enumerate(zip(config.class_names, percents)):
            lines.append((idx, f"{name}: {p:.1f}%"))
            stats.append({"name": name, "percent": float(p)})

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        line_height = 0
        max_width = 0
        for _, line in lines:
            (w, h), _ = cv2.getTextSize(line, font, font_scale, thickness)
            max_width = max(max_width, w)
            line_height = max(line_height, h)

        padding = 8
        color_box_size = max(12, line_height - 2)
        text_offset = color_box_size + 6
        box_w = text_offset + max_width + padding * 2
        box_h = line_height * len(lines) + padding * 2 + 4 * (len(lines) - 1)

        # Рисуем таблицу в левом верхнем углу
        x0, y0 = 10, 10
        x1, y1 = x0 + box_w, y0 + box_h
        cv2.rectangle(colored, (x0, y0), (x1, y1), (0, 0, 0), thickness=-1)

        y_text = y0 + padding + line_height
        for idx, line in lines:
            # Цветной квадрат — классы в config в BGR
            cx, cy = x0 + padding, y_text - line_height + 2
            color_bgr = tuple(int(c) for c in config.class_colors[idx])
            cv2.rectangle(colored, (cx, cy), (cx + color_box_size, cy + color_box_size), color_bgr, thickness=-1)
            cv2.rectangle(colored, (cx, cy), (cx + color_box_size, cy + color_box_size), (255, 255, 255), thickness=1)
            cv2.putText(colored, line, (x0 + padding + text_offset, y_text), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
            y_text += line_height + 4

        # 7. Сохраняем статистику в задаче, конвертируем в RGB и сохраняем изображение
        tasks[task_id]["stats"] = stats
        colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
        os.makedirs("server_results", exist_ok=True)
        result_path = f"server_results/{task_id}_result.png"
        cv2.imwrite(result_path, colored)

        # 6. Обновляем статус задачи
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result_file"] = result_path
        print(f"Задача {task_id} готова! Результат: {result_path}")

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        print(f"Ошибка в алгоритме: {e}")


@app.post("/api/start_analysis")
async def start_analysis(
        background_tasks: BackgroundTasks,
        algorithm_id: str = Form(...),
        user_id: str = Form(...),
        file: UploadFile = File(...)
):
    task_id = f"res_{uuid.uuid4()}"

    # Сохраняем входящий файл
    os.makedirs("server_uploads", exist_ok=True)
    # Сохраняем под безопасным именем, чтобы не зависеть от оригинального filename
    suffix = (Path(file.filename).suffix or "").lower()
    if suffix not in [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".geotiff"]:
        suffix = ".bin"
    input_path = str(Path("server_uploads") / f"{task_id}{suffix}")
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Создаем запись о задаче
    tasks[task_id] = {"status": "processing", "algo": algorithm_id}

    # Запускаем алгоритм в фоне, чтобы не блокировать HTTP-ответ
    background_tasks.add_task(run_real_algorithm, task_id, input_path, algorithm_id)

    return {"task_id": task_id}


@app.get("/api/task/{task_id}/status")
async def get_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return {"status": "failed", "error": "Not found"}
    return {"status": task["status"]}


@app.get("/api/task/{task_id}/result")
async def get_result(task_id: str):
    task = tasks.get(task_id)
    if task and task["status"] == "completed":
        from fastapi.responses import FileResponse
        return FileResponse(task["result_file"])
    return {"error": "Not ready"}


@app.get("/api/task/{task_id}/stats")
async def get_stats(task_id: str):
    """Возвращает статистику по классам для задачи."""
    task = tasks.get(task_id)
    if not task or task.get("status") != "completed" or "stats" not in task:
        return {"error": "Not ready"}
    return {"stats": task["stats"]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)