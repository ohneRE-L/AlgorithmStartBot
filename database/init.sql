-- Очистка старой схемы (удаление таблиц в правильном порядке)
DROP TABLE IF EXISTS results CASCADE;
DROP TABLE IF EXISTS analysis_requests CASCADE;
DROP TABLE IF EXISTS source_images CASCADE;
DROP TABLE IF EXISTS regions CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;

-- 1. Таблица пользователей
CREATE TABLE users (
    telegram_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    role VARCHAR(50) NOT NULL CHECK (role IN ('OPERATOR', 'MODERATOR')),
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Таблица регионов
CREATE TABLE regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL
);

-- 3. Таблица исходных файлов
CREATE TABLE source_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL,
    file_size BIGINT,
    file_extension VARCHAR(10),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Таблица заявок на анализ
CREATE TABLE analysis_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
    region_id UUID REFERENCES regions(id),
    source_image_id UUID NOT NULL REFERENCES source_images(id),
    algorithm_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'ERROR')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Таблица результатов
CREATE TABLE results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_request_id UUID NOT NULL REFERENCES analysis_requests(id) ON DELETE CASCADE,
    metadata JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX idx_requests_user ON analysis_requests(user_id);
CREATE INDEX idx_requests_status ON analysis_requests(status);

-- Базовое наполнение (необязательно)
INSERT INTO regions (name, code) VALUES ('Неизвестный регион', '00');