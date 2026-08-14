-- DDL para el esquema relacional de Pomodoro en 3D-Moai (PostgreSQL / Supabase)

-- 1. Tabla de Dispositivos (Registro de Hardware)
CREATE TABLE IF NOT EXISTS dispositivos (
    device_id VARCHAR(50) PRIMARY KEY,       -- Dirección MAC de la ESP32 (ej: "240ac4041b30")
    user_id INTEGER NOT NULL,                -- ID de usuario en tu plataforma 3D-Moai
    product_type VARCHAR(50) DEFAULT 'Pomodoro Pro', -- Nombre/tipo del producto
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexar last_seen_at y user_id para búsquedas rápidas en panel de administración
CREATE INDEX IF NOT EXISTS idx_dispositivos_user_id ON dispositivos(user_id);
CREATE INDEX IF NOT EXISTS idx_dispositivos_last_seen ON dispositivos(last_seen_at);

-- 2. Tabla de Configuraciones del Pomodoro (Unica por dispositivo)
CREATE TABLE IF NOT EXISTS pomodoro_configuraciones (
    device_id VARCHAR(50) PRIMARY KEY REFERENCES dispositivos(device_id) ON DELETE CASCADE,
    tiempo_focus INTEGER NOT NULL DEFAULT 1500,        -- Tiempo en segundos (por defecto 25min)
    tiempo_descanso_corto INTEGER NOT NULL DEFAULT 300, -- Tiempo en segundos (por defecto 5min)
    tiempo_descanso_largo INTEGER NOT NULL DEFAULT 900, -- Tiempo en segundos (por defecto 15min)
    descanso_largo_activo BOOLEAN NOT NULL DEFAULT TRUE,
    ciclos_para_descanso_largo INTEGER NOT NULL DEFAULT 4,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla de Estadísticas de Pomodoro (Telemetría de Ciclos, Pausas y Reacciones)
CREATE TABLE IF NOT EXISTS pomodoro_estadisticas (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL REFERENCES dispositivos(device_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    tipo_sesion VARCHAR(50) NOT NULL,        -- 'focus', 'descanso_corto', 'descanso_largo', 'pausa_focus', 'reaccion_rojo'
    ciclo_num INTEGER DEFAULT 0,              -- Consecutivo del ciclo
    duracion_s INTEGER NOT NULL,             -- Duración activa en segundos
    forzado INTEGER DEFAULT 0                -- 1 si fue cancelado, 0 si se completó con éxito
);

-- Indexar por dispositivo y fecha para agilizar reportes y gráficos
CREATE INDEX IF NOT EXISTS idx_stats_device_date ON pomodoro_estadisticas(device_id, timestamp);
