"""
Запуск локального Telegram Bot API с вашими api_id и api_hash.

Нужен бинарник telegram-bot-api (скачать с https://github.com/tdlib/telegram-bot-api/releases).
Добавьте его в PATH или положите в папку с этим скриптом.

В token.env должны быть:
  TELEGRAM_API_ID=...
  TELEGRAM_API_HASH=...
  LOCAL_BOT_API_URL=http://localhost:8081  # тогда бот подключится к этому серверу
"""
import os
import sys
import subprocess
from pathlib import Path

# Загружаем переменные из token.env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / "token.env")
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
PORT = 8081

if not API_ID or not API_HASH:
    print("Заполните в token.env: TELEGRAM_API_ID и TELEGRAM_API_HASH (из my.telegram.org)")
    sys.exit(1)

# Ищем telegram-bot-api в PATH или рядом со скриптом
local_dir = Path(__file__).parent
if sys.platform == "win32":
    exe_name = "telegram-bot-api.exe"
else:
    exe_name = "telegram-bot-api"

exe = exe_name
local_exe = local_dir / exe_name
if local_exe.exists():
    exe = str(local_exe)
else:
    import shutil
    in_path = shutil.which(exe_name)
    if in_path:
        exe = in_path
    else:
        print(f"Не найден {exe_name}.")
        print("Положите бинарник в папку проекта или добавьте в PATH.")
        print("Подробнее: LOCAL_BOT_API_SETUP.md")
        sys.exit(1)

args = [
    exe,
    "--local",
    f"--api-id={API_ID}",
    f"--api-hash={API_HASH}",
    f"--http-port={PORT}",
]

# Запуск в фоне, чтобы после выхода из скрипта сервер продолжал работать
kwargs = {
    "cwd": str(local_dir),
    "stdin": subprocess.DEVNULL,
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
}
if sys.platform == "win32":
    kwargs["creationflags"] = (
        subprocess.CREATE_NO_WINDOW
        | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    )
else:
    kwargs["start_new_session"] = True

proc = subprocess.Popen(args, **kwargs)
pid_file = local_dir / "local_bot_api.pid"
try:
    pid_file.write_text(str(proc.pid), encoding="utf-8")
except Exception:
    pass

print("Локальный Bot API запущен в фоне.")
print(f"  Адрес: http://127.0.0.1:{PORT}")
print(f"  PID:   {proc.pid} (сохранён в local_bot_api.pid)")
print()
print("Теперь в этом же или в другом терминале запустите бота:")
print("  python main.py")
print()
print("Чтобы остановить сервер: завершите процесс telegram-bot-api или выполните")
print("  taskkill /PID", proc.pid, "/F")
