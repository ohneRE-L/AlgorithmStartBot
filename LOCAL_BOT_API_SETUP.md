# Инструкция по установке локального сервера Bot API на VPS

Эта инструкция поможет вам установить локальный сервер Telegram Bot API на виртуальном сервере (VPS) с Linux для поддержки загрузки файлов до 2000 МБ.

## Требования

- VPS с Linux (Ubuntu 20.04+ или Debian 11+)
- Минимум 2 ГБ RAM
- Минимум 10 ГБ свободного места на диске
- Root доступ или пользователь с правами sudo

## Шаг 1: Подготовка сервера

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y build-essential cmake git libssl-dev zlib1g-dev gperf libreadline-dev libc++-dev
```

## Шаг 2: Получение API ID и API Hash

1. Перейдите на https://my.telegram.org/apps
2. Войдите с вашим номером телефона (международный формат: +79991234567)
3. Введите код подтверждения из Telegram
4. Если приложение еще не создано, нажмите "Create new application"
5. Заполните форму:
   - **App title:** `Bot API Server`
   - **Short name:** `botapi` (уникальное имя, только латиница и цифры)
   - **URL:** `http://localhost`
   - **Platform:** `Other`
6. Сохраните `api_id` и `api_hash`

**Если появляется ошибка "Error":**
- Попробуйте другое Short name (оно должно быть уникальным)
- Очистите кэш браузера (Ctrl+Shift+Delete)
- Попробуйте другой браузер или режим инкогнито

## Шаг 3: Установка Telegram Bot API

**Если у вас менее 4 ГБ RAM, сначала увеличьте swap:**

```bash
# Проверьте текущий swap
free -h

# Создайте файл подкачки 4 ГБ
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Сделайте постоянным
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Вариант 1: Генератор инструкций (рекомендуется)

1. Перейдите на https://tdlib.github.io/telegram-bot-api/build.html
2. Выберите вашу ОС и дистрибутив
3. Выберите место установки (`/usr/local/bin`)
4. Выполните команды по порядку

### Вариант 2: Ручная сборка (если генератор не подходит)

```bash
cd telegram-bot-api
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/usr/local ..
cmake --build . --target install -j1
```

**Важно:** Используйте `-j1` (одна параллельная задача) если у вас мало RAM. Это медленнее, но безопаснее.

### Вариант 3: Готовые бинарники (рекомендуется при нехватке RAM)

1. Скачайте бинарник для вашей ОС
2. Установите зависимости:

```bash
# Debian 11-12:
sudo apt install libc++-dev

# Ubuntu 22.04:
sudo apt install libc++-14-dev

# Ubuntu 24.04:
sudo apt install libc++-18-dev
```

3. Скопируйте бинарник:

```bash
sudo cp telegram-bot-api /usr/local/bin/
sudo chmod +x /usr/local/bin/telegram-bot-api
```

### Проверка установки

```bash
telegram-bot-api --version
```

### Тестовый запуск

```bash
telegram-bot-api --local --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH
```

В другом терминале проверьте:

```bash
curl http://localhost:8081
```

Должен вернуться: `{"ok":false,"error_code":404,"description":"Not Found"}`

Остановите тестовый запуск (Ctrl+C).

## Шаг 4: Настройка systemd сервиса

Создайте пользователя:

```bash
sudo useradd -r -s /bin/false telegram-bot-api
sudo mkdir -p /var/lib/telegram-bot-api
sudo chown telegram-bot-api:telegram-bot-api /var/lib/telegram-bot-api
```

Создайте сервис:

```bash
sudo nano /etc/systemd/system/telegram-bot-api.service
```

Вставьте (замените `YOUR_API_ID` и `YOUR_API_HASH`):

```ini
[Unit]
Description=Telegram Bot API Local Server
After=network.target

[Service]
Type=simple
User=telegram-bot-api
Group=telegram-bot-api
WorkingDirectory=/var/lib/telegram-bot-api
ExecStart=/usr/local/bin/telegram-bot-api --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot-api
sudo systemctl start telegram-bot-api
sudo systemctl status telegram-bot-api
```

## Шаг 5: Настройка бота

### Отключение от официального API

```bash
curl https://api.telegram.org/bot<TOKEN>/logOut
```

Должен вернуться: `{"ok":true,"result":true}`

### Обновление конфигурации

В файле `token.env` добавьте:

```env
LOCAL_BOT_API_URL=http://localhost:8081
```

Перезапустите бота. В логах должно появиться:
```
Используется локальный сервер Bot API: http://localhost:8081
Максимальный размер файла: 2000 МБ
```

## Важно: Работа с файлами

При использовании локального сервера в режиме `--local`:

- **Метод `getFile` возвращает абсолютный локальный путь** вместо `file_path` для скачивания
- Файлы сохраняются в `/var/lib/telegram-bot-api/<токен_бота>/`
- **Не нужно скачивать файлы** — они уже на диске
- Убедитесь, что пользователь бота имеет права на чтение в рабочей директории

## Устранение неполадок

**Сервис не запускается:**
```bash
sudo journalctl -u telegram-bot-api -n 50
```

**Порт занят:**
```bash
sudo netstat -tulpn | grep 8081
```

**Бот не подключается:**
- Проверьте статус: `sudo systemctl status telegram-bot-api`
- Проверьте URL в конфигурации
- Проверьте файрвол: `sudo ufw status`

## Полезные ссылки

- [Генератор инструкций для компиляции](https://tdlib.github.io/telegram-bot-api/build.html)
- [Официальный репозиторий](https://github.com/tdlib/telegram-bot-api)
- [Получение API ID и Hash](https://my.telegram.org/apps)
