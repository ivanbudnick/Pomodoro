import os
import sqlite3
import threading
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'pomodoro.db')

class DatabaseCursorWrapper:
    def __init__(self, cursor, is_pg):
        self._cursor = cursor
        self._is_pg = is_pg
        
    def __getattr__(self, name):
        return getattr(self._cursor, name)
        
    def execute(self, query, params=None):
        if self._is_pg:
            query = query.replace('?', '%s')
            query = query.replace('date(timestamp)', 'timestamp::date')
        if params is None:
            return self._cursor.execute(query)
        return self._cursor.execute(query, params)

class ConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn
        self._is_pg = not isinstance(conn, sqlite3.Connection)
        
    def __getattr__(self, name):
        return getattr(self._conn, name)
        
    def cursor(self, *args, **kwargs):
        cursor = self._conn.cursor(*args, **kwargs)
        return DatabaseCursorWrapper(cursor, self._is_pg)
        
    def __enter__(self):
        self._conn.__enter__()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)

def get_db_connection():
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
    if db_url and (db_url.startswith('postgres://') or db_url.startswith('postgresql://')):
        try:
            import psycopg2
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
            conn = psycopg2.connect(db_url)
            return ConnectionWrapper(conn)
        except Exception as e:
            print("[DB] Fallo al conectar a Postgres. Usando SQLite local.", e)
            
    import sqlite3
    if os.environ.get('VERCEL') == '1':
        return ConnectionWrapper(sqlite3.connect('/tmp/pomodoro.db'))
    return ConnectionWrapper(sqlite3.connect(DB_PATH))

def is_postgres(conn):
    # En nuestro ConnectionWrapper, el objeto real es _conn
    return not isinstance(conn._conn if hasattr(conn, '_conn') else conn, sqlite3.Connection)

def init_db():
    """Inicializa la base de datos (PostgreSQL o SQLite) con soporte para tipos de sesión Pomodoro Pro, métricas y avance forzado"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_pg = is_postgres(conn)
    serial_type = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    datetime_type = "TIMESTAMP" if is_pg else "DATETIME"
    real_type = "REAL"
    integer_type = "INTEGER"
    text_type = "TEXT"
    
    # Crear tabla de sesiones
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS sesiones_pomodoro (
            id {serial_type},
            timestamp {datetime_type} DEFAULT CURRENT_TIMESTAMP,
            dispositivo {text_type},
            tipo_sesion {text_type} DEFAULT 'focus',
            ciclo_num {integer_type},
            duracion_s {integer_type},
            configuracion_id {integer_type},
            forzado {integer_type} DEFAULT 0
        )
    ''')
    
    # Crear tabla de configuraciones
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS configuraciones (
            id {serial_type},
            timestamp {datetime_type} DEFAULT CURRENT_TIMESTAMP,
            tiempo_focus {integer_type},
            tiempo_descanso_corto {integer_type},
            tiempo_descanso_largo {integer_type},
            descanso_largo_activo {integer_type},
            ciclos_para_descanso_largo {integer_type}
        )
    ''')
    
    # Crear tabla de pausas
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS pausas (
            id {serial_type},
            timestamp {datetime_type} DEFAULT CURRENT_TIMESTAMP,
            fase {text_type},
            tiempo_transcurrido_s {integer_type},
            porcentaje_transcurrido {real_type},
            duracion_pausa_s {integer_type},
            configuracion_id {integer_type}
        )
    ''')

    # Crear tabla de tiempos de reacción a las alertas
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS tiempos_reaccion (
            id {serial_type},
            timestamp {datetime_type} DEFAULT CURRENT_TIMESTAMP,
            tipo_alerta {text_type},
            duracion_alerta_s {real_type},
            configuracion_id {integer_type}
        )
    ''')

    # Crear tabla de eventos de ciclos (inicio, fin, cancelación, forzado)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS eventos_ciclos (
            id {serial_type},
            timestamp {datetime_type} DEFAULT CURRENT_TIMESTAMP,
            fase {text_type},
            evento {text_type},
            tiempo_activo_s {integer_type},
            configuracion_id {integer_type},
            forzado {integer_type} DEFAULT 0
        )
    ''')
    
    if not is_pg:
        # Migraciones legacy solo para SQLite
        try:
            cursor.execute("PRAGMA table_info(ciclos_rojos)")
            legacy_exists = cursor.fetchall()
            if legacy_exists:
                cursor.execute('''
                    INSERT INTO sesiones_pomodoro (timestamp, dispositivo, tipo_sesion, ciclo_num, duracion_s)
                    SELECT timestamp, dispositivo, 'focus', ciclo_num, duracion_s FROM ciclos_rojos
                ''')
                cursor.execute("DROP TABLE ciclos_rojos")
        except:
            pass

        try:
            cursor.execute("PRAGMA table_info(sesiones_pomodoro)")
            cols = [row[1] for row in cursor.fetchall()]
            if "configuracion_id" not in cols:
                cursor.execute("ALTER TABLE sesiones_pomodoro ADD COLUMN configuracion_id INTEGER")
            if "forzado" not in cols:
                cursor.execute("ALTER TABLE sesiones_pomodoro ADD COLUMN forzado INTEGER DEFAULT 0")
        except:
            pass

        try:
            cursor.execute("PRAGMA table_info(eventos_ciclos)")
            cols_ciclos = [row[1] for row in cursor.fetchall()]
            if "forzado" not in cols_ciclos:
                cursor.execute("ALTER TABLE eventos_ciclos ADD COLUMN forzado INTEGER DEFAULT 0")
        except:
            pass
            
    # Insertar configuración por defecto si la tabla está vacía
    cursor.execute("SELECT COUNT(*) FROM configuraciones")
    if cursor.fetchone()[0] == 0:
        try:
            cursor.execute('''
                INSERT INTO configuraciones (tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo)
                VALUES (1500, 300, 900, 1, 4)
            ''')
        except Exception as e:
            print("[BD INIT ERROR] No se pudo insertar configuración por defecto:", e)
            
    conn.commit()
    conn.close()

init_db()

# --- PLANTILLA DASHBOARD CON ESTÉTICA UNIFICADA Y CHART.JS ---
HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pomodoro esp32 - Panel de Control</title>
    <!-- Chart.js para gráficos interactivos -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #06080f;
            --muted: #8a8f98;
            --text: #f3f4f6;
            --border: rgba(255, 255, 255, 0.06);
            --card-bg: rgba(255, 255, 255, 0.015);
            
            --focus: #e05a5a;
            --descanso-corto: #5b8ce0;
            --descanso-largo: #52be90;
            --streak: #d99b26;
            
            --font: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(224, 90, 90, 0.03) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(82, 190, 144, 0.03) 0px, transparent 50%),
                radial-gradient(at 50% 50%, rgba(91, 140, 224, 0.02) 0px, transparent 60%);
            color: var(--text);
            font-family: var(--font);
            min-height: 100vh;
            display: flex;
        }

        /* SIDEBAR */
        .sidebar {
            width: 260px;
            background: rgba(10, 14, 23, 0.5);
            border-right: 1px solid var(--border);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            display: flex;
            flex-direction: column;
            padding: 40px 20px;
            position: fixed;
            top: 0;
            bottom: 0;
            left: 0;
            z-index: 100;
        }

        .sidebar-brand {
            margin-bottom: 40px;
        }

        .sidebar-brand h2 {
            font-size: 1.25rem;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.5px;
            margin-top: 4px;
        }

        .sidebar-menu {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .menu-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: 12px;
            color: var(--muted);
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s ease;
            cursor: pointer;
            border: 1px solid transparent;
        }

        .menu-item svg {
            opacity: 0.7;
            transition: opacity 0.2s;
        }

        .menu-item:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.02);
        }

        .menu-item:hover svg {
            opacity: 1;
        }

        .menu-item.active {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.08);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        .menu-item.active svg {
            opacity: 1;
        }

        /* MAIN CONTENT */
        .main-content {
            margin-left: 260px;
            flex: 1;
            padding: 40px 48px;
            max-width: calc(100vw - 260px);
            box-sizing: border-box;
        }

        .tab-view {
            display: none;
            width: 100%;
            animation: fadeIn 0.3s ease-in-out;
        }

        .tab-view.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
        }

        .brand-tag {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: var(--muted);
            font-size: 0.75rem;
            font-weight: 500;
            margin-bottom: 12px;
            user-select: none;
        }

        h1 {
            font-size: 1.75rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 6px;
            letter-spacing: -0.5px;
        }

        .subtitle {
            font-size: 0.85rem;
            color: var(--muted);
            font-weight: 400;
        }

        /* GRID DE MÉTRICAS */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 24px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            border-color: rgba(255, 255, 255, 0.12);
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; width: 100%; height: 3px;
        }

        .stat-card.red::before { background: var(--focus); }
        .stat-card.blue::before { background: var(--descanso-corto); }
        .stat-card.green::before { background: var(--descanso-largo); }
        .stat-card.gold::before { background: var(--streak); }

        .stat-value {
            font-size: 2.5rem;
            font-weight: 300;
            color: #ffffff;
            line-height: 1.1;
            margin-bottom: 8px;
        }

        .stat-label {
            font-size: 0.8rem;
            font-weight: 500;
            color: var(--muted);
        }

        /* SECCIÓN DE GRÁFICOS */
        .charts-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 24px;
            margin-bottom: 40px;
        }

        @media (min-width: 992px) {
            .charts-grid {
                grid-template-columns: 2fr 1fr;
            }
        }

        .chart-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }

        .chart-card h3 {
            font-size: 0.95rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* TABLA DE HISTORIAL */
        .table-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            overflow-x: auto;
            margin-bottom: 40px;
        }

        .table-card h3 {
            font-size: 0.95rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 20px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th, td {
            padding: 14px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }

        th {
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--muted);
        }

        td {
            font-size: 0.85rem;
            color: #cbd5e1;
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.005);
        }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 500;
        }

        .badge.focus {
            background: rgba(224, 90, 90, 0.08);
            color: #e05a5a;
            border: 1px solid rgba(224, 90, 90, 0.2);
        }

        .badge.descanso_corto {
            background: rgba(91, 140, 224, 0.08);
            color: #5b8ce0;
            border: 1px solid rgba(91, 140, 224, 0.2);
        }

        .badge.descanso_largo {
            background: rgba(82, 190, 144, 0.08);
            color: #52be90;
            border: 1px solid rgba(82, 190, 144, 0.2);
        }

        /* ESTILOS CONFIGURACIÓN (TIPO DASHBOARD.HTML) */
        .config-grid {
            width: 100%;
            display: grid;
            grid-template-columns: 1fr;
            gap: 32px;
            margin-top: 30px;
            margin-bottom: 40px;
        }
        @media (min-width: 1024px) {
            .config-grid { grid-template-columns: repeat(3, 1fr); gap: 40px; }
        }
        .config-column { display: flex; flex-direction: column; align-items: center; }
        .column-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        .status-dot.focus { background-color: var(--focus); }
        .status-dot.short { background-color: var(--descanso-corto); }
        .status-dot.long { background-color: var(--descanso-largo); }
        .config-column h2 { font-size: 0.95rem; font-weight: 600; color: #fff; }
        .time-picker { width: 100%; max-width: 280px; }
        .time-picker-grid { display: grid; grid-template-columns: 1fr auto 1fr; justify-items: center; align-items: center; }
        .picker-label { font-size: 0.75rem; color: var(--muted); font-weight: 500; margin-bottom: 6px; }
        .picker-separator-label { width: 16px; }
        .picker-box-wrapper { grid-column: span 3; width: 100%; }
        .picker-box {
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(255, 255, 255, 0.015);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 16px 20px;
            transition: border-color 0.3s, background-color 0.3s;
        }
        .picker-box:focus-within { border-color: rgba(255, 255, 255, 0.15); background: rgba(255, 255, 255, 0.03); }
        .digit-input {
            background: transparent;
            border: none;
            color: #fff;
            font-size: 3.5rem;
            font-weight: 300;
            width: 2.2ch;
            text-align: center;
            outline: none;
            font-family: inherit;
            font-variant-numeric: tabular-nums;
            -moz-appearance: textfield;
        }
        .digit-input::-webkit-outer-spin-button, .digit-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
        .picker-colon { font-size: 3rem; color: rgba(255, 255, 255, 0.15); font-weight: 300; margin: 0 2px; line-height: 1; transform: translateY(-4px); }
        .long-break-header-row { display: flex; align-items: center; justify-content: space-between; width: 100%; max-width: 280px; margin-bottom: 16px; }
        .long-break-header-row .column-header { margin-bottom: 0; }
        .switch { position: relative; display: inline-block; width: 42px; height: 22px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(255, 255, 255, 0.06);
            transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
            border-radius: 22px;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 14px;
            width: 14px;
            left: 3px;
            bottom: 3px;
            background-color: #f3f4f6;
            transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
            border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--descanso-largo); }
        input:checked + .slider:before { transform: translateX(20px); background-color: #06080f; }
        .cycles-container { width: 100%; max-width: 280px; display: flex; align-items: center; justify-content: space-between; margin-top: 20px; transition: opacity 0.3s; }
        .cycles-label { font-size: 0.8rem; color: var(--muted); }
        .cycles-input-box { background: rgba(255, 255, 255, 0.015); border: 1px solid var(--border); border-radius: 10px; padding: 6px 12px; width: 64px; }
        .cycles-input-box input { width: 100%; background: transparent; border: none; color: #fff; font-family: inherit; font-size: 0.9rem; font-weight: 500; text-align: center; outline: none; }
        .action-row { width: 100%; display: flex; justify-content: center; margin-top: 20px; }
        .btn-save {
            background: #fff;
            color: #06080f;
            border: none;
            border-radius: 14px;
            padding: 14px 40px;
            font-family: inherit;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: transform 0.2s, background-color 0.2s;
        }
        .btn-save:hover { background-color: #f3f4f6; transform: translateY(-2px); }
        .btn-save:active { transform: translateY(1px); }

        .gesture-legend {
            background: rgba(10, 14, 23, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 20px;
            width: 100%;
            max-width: 800px;
            margin: 40px auto 0 auto;
        }
        .legend-header { font-size: 0.8rem; font-weight: 600; color: #fff; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
        .legend-info-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 14px;
            height: 14px;
            border: 1.5px solid var(--muted);
            border-radius: 50%;
            font-size: 0.65rem;
            font-weight: 700;
            color: var(--muted);
        }
        .legend-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .legend-item { display: flex; flex-direction: column; gap: 2px; border-left: 2px solid rgba(255, 255, 255, 0.08); padding-left: 10px; }
        .legend-cmd { font-size: 0.75rem; font-weight: 600; color: #fff; }
        .legend-desc { font-size: 0.7rem; color: var(--muted); line-height: 1.3; }

        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 1000;
            background: rgba(82, 190, 144, 0.08);
            border: 1px solid rgba(82, 190, 144, 0.2);
            color: #52be90;
            font-size: 0.8rem;
            font-weight: 500;
            padding: 12px 20px;
            border-radius: 12px;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            opacity: 0;
            transform: translateY(20px) scale(0.95);
            transition: all 0.3s;
            pointer-events: none;
        }
        .toast.show { opacity: 1; transform: translateY(0) scale(1); }

        @media (max-width: 768px) {
            body {
                flex-direction: column;
            }
            .sidebar {
                width: 100%;
                height: auto;
                position: relative;
                padding: 20px;
                border-right: none;
                border-bottom: 1px solid var(--border);
            }
            .sidebar-brand {
                margin-bottom: 15px;
                text-align: center;
            }
            .sidebar-menu {
                flex-direction: row;
                justify-content: center;
                gap: 15px;
            }
            .main-content {
                margin-left: 0;
                padding: 24px;
                max-width: 100vw;
            }
            .legend-list {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <!-- SIDEBAR -->
    <div class="sidebar">
        <div class="sidebar-brand">
            <span class="brand-tag">pomodoro esp32</span>
            <h2>Control Panel</h2>
        </div>
        <div class="sidebar-menu">
            <a class="menu-item active" id="btn-metricas" onclick="switchTab('metricas')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
                Métricas
            </a>
            <a class="menu-item" id="btn-config" onclick="switchTab('config')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                Configuración
            </a>
        </div>
    </div>

    <!-- MAIN CONTENT -->
    <div class="main-content">
        <!-- VISTA DE MÉTRICAS -->
        <div id="tab-metricas" class="tab-view active">
            <div class="header">
                <span class="brand-tag">Estadísticas pomodoro</span>
                <h1>Panel de rendimiento</h1>
                <p class="subtitle">Monitoreo de sesiones y métricas de productividad en tiempo real</p>
            </div>

            <!-- TARJETAS DE ESTADÍSTICAS -->
            <div class="stats-grid">
                <div class="stat-card red">
                    <div class="stat-value">{{ total_focus }}</div>
                    <div class="stat-label">Sesiones de enfoque</div>
                </div>
                <div class="stat-card blue">
                    <div class="stat-value">{{ total_minutos_focus }}m</div>
                    <div class="stat-label">Tiempo total de enfoque</div>
                </div>
                <div class="stat-card gold">
                    <div class="stat-value">{{ racha_actual }}</div>
                    <div class="stat-label">Racha actual (días)</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-value">{{ racha_maxima }}</div>
                    <div class="stat-label">Mejor racha (días)</div>
                </div>
            </div>

            <!-- SECCIÓN DE GRÁFICOS -->
            <div class="charts-grid">
                <div class="chart-card">
                    <h3>Minutos de enfoque por día</h3>
                    <canvas id="chartDias" height="180"></canvas>
                </div>
                <div class="chart-card">
                    <h3>Distribución de sesiones</h3>
                    <canvas id="chartTipos" height="180"></canvas>
                </div>
            </div>

            <!-- TABLA DE HISTORIAL -->
            <div class="table-card">
                <h3>Historial de sesiones</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Id</th>
                            <th>Fecha y hora</th>
                            <th>Tipo de sesión</th>
                            <th>Ciclo</th>
                            <th>Duración</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for s in sesiones %}
                        <tr>
                            <td>#{{ s[0] }}</td>
                            <td>{{ s[1] }}</td>
                            <td>
                                {% if s[3] == 'focus' %}
                                    <span class="badge focus">Enfoque</span>
                                {% elif s[3] == 'descanso_largo' %}
                                    <span class="badge descanso_largo">Descanso largo</span>
                                {% else %}
                                    <span class="badge descanso_corto">Descanso corto</span>
                                {% endif %}
                            </td>
                            <td>Ciclo #{{ s[4] }}</td>
                            <td>
                                {{ s[5] }} seg
                                {% if s[6] == 1 %}
                                    <span style="font-size: 0.75rem; color: #fb923c; font-weight: 500; margin-left: 4px;">(Forzado)</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="5" style="text-align: center; color: var(--muted); padding: 32px;">
                                No hay sesiones registradas aún. Completa una sesión de enfoque en tu dispositivo.
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <!-- TARJETAS DE MÉTRICAS AVANZADAS -->
            <h2 style="font-size: 1.25rem; margin-top: 40px; margin-bottom: 20px; font-weight: 600; color: #ffffff;">Métricas Avanzadas (Analítica)</h2>
            <div class="stats-grid">
                <div class="stat-card red">
                    <div class="stat-value">{{ avg_reaccion_focus }}s</div>
                    <div class="stat-label">Reac. Post-Focus Promedio</div>
                </div>
                <div class="stat-card blue">
                    <div class="stat-value">{{ avg_reaccion_corto }}s</div>
                    <div class="stat-label">Reac. Post-D. Corto Promedio</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-value">{{ avg_reaccion_largo }}s</div>
                    <div class="stat-label">Reac. Post-D. Largo Promedio</div>
                </div>
                <div class="stat-card gold">
                    <div class="stat-value">{{ total_pausas }} <span style="font-size: 0.9rem; color: var(--muted); font-weight: 400;">({{ avg_duracion_pausa }}s avg)</span></div>
                    <div class="stat-label">Pausas registradas</div>
                </div>
                <div class="stat-card red" style="background: rgba(244, 63, 94, 0.015); border-color: rgba(244, 63, 94, 0.15);">
                    <div class="stat-value">{{ total_forzados }}</div>
                    <div class="stat-label">Avances Forzados</div>
                </div>
            </div>

            <!-- DETALLE DE TELEMETRÍA -->
            <div class="charts-grid" style="margin-top: 40px; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));">
                <!-- TABLA DE PAUSAS -->
                <div class="table-card">
                    <h3>Detalle de Pausas Recientes</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Fecha</th>
                                <th>Fase</th>
                                <th>Avance al pausar</th>
                                <th>Pausa</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for p in ultimas_pausas %}
                            <tr>
                                <td>{{ p[1].split(' ')[1] if ' ' in p[1] else p[1] }}</td>
                                <td>
                                    {% if p[2] == 'FOCUS' %}
                                        <span class="badge focus">Enfoque</span>
                                    {% elif p[2] == 'DESCANSO_CORTO' %}
                                        <span class="badge descanso_corto">D. Corto</span>
                                    {% else %}
                                        <span class="badge descanso_largo">D. Largo</span>
                                    {% endif %}
                                </td>
                                <td>{{ p[3] }}s ({{ "%.1f"|format(p[4]) }}%)</td>
                                <td style="color: #f43f5e; font-weight: 600;">{{ p[5] }}s</td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="4" style="text-align: center; color: var(--muted); padding: 16px;">
                                    Sin pausas registradas.
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <!-- TABLA DE TIEMPOS DE REACCIÓN -->
                <div class="table-card">
                    <h3>Detalle de Reacciones a Alertas</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Fecha</th>
                                <th>Tipo de Alerta</th>
                                <th>Reacción</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for r in ultimas_reacciones %}
                            <tr>
                                <td>{{ r[1].split(' ')[1] if ' ' in r[1] else r[1] }}</td>
                                <td>
                                    {% if r[2] == 'POST_FOCUS' %}
                                        <span class="badge focus">Post-Focus</span>
                                    {% elif r[2] == 'POST_DESCANSO_CORTO' %}
                                        <span class="badge descanso_corto">Post-D. Corto</span>
                                    {% else %}
                                        <span class="badge descanso_largo">Post-D. Largo</span>
                                    {% endif %}
                                </td>
                                <td style="color: #fbbf24; font-weight: 600;">{{ "%.2f"|format(r[3]) }}s</td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="3" style="text-align: center; color: var(--muted); padding: 16px;">
                                    Sin tiempos de reacción.
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <!-- TABLA DE EVENTOS DE CICLO -->
                <div class="table-card" style="grid-column: 1 / -1;">
                    <h3>Bitácora de Ciclos Recientes</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Fecha</th>
                                <th>Fase</th>
                                <th>Evento</th>
                                <th>Duración Activa</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for c in ultimos_ciclos %}
                            <tr>
                                <td>{{ c[1] }}</td>
                                <td>
                                    {% if c[2] == 'FOCUS' %}
                                        <span class="badge focus">Enfoque</span>
                                    {% elif c[2] == 'DESCANSO_CORTO' %}
                                        <span class="badge descanso_corto">D. Corto</span>
                                    {% else %}
                                        <span class="badge descanso_largo">D. Largo</span>
                                    {% endif %}
                                </td>
                                <td>
                                    {% if c[3] == 'INICIADO' %}
                                        <span style="color: #60a5fa; font-weight: 500;">Iniciado</span>
                                    {% elif c[3] == 'COMPLETADO' %}
                                        <span style="color: #34d399; font-weight: 600;">Completado</span>
                                    {% elif c[3] == 'FORZADO' %}
                                        <span style="color: #fb923c; font-weight: 600;">Avance Forzado</span>
                                    {% else %}
                                        <span style="color: #f87171; font-weight: 500;">Cancelado (Reset)</span>
                                    {% endif %}
                                </td>
                                <td>{{ c[4] }}s</td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="4" style="text-align: center; color: var(--muted); padding: 16px;">
                                    Sin eventos de ciclos registrados.
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- VISTA DE CONFIGURACIÓN -->
        <div id="tab-config" class="tab-view">
            <div class="header">
                <span class="brand-tag">pomodoro esp32</span>
                <h1>Configuración de intervalos</h1>
                <p class="subtitle">Personaliza los tiempos de enfoque y descanso de tu dispositivo</p>
            </div>

            <div class="config-grid">
                <!-- FOCUS COLUMN -->
                <div class="config-column">
                    <div class="column-header">
                        <span class="status-dot focus"></span>
                        <h2>Sesión de enfoque</h2>
                    </div>
                    <div class="time-picker">
                        <div class="time-picker-grid">
                            <span class="picker-label">min</span>
                            <span class="picker-separator-label"></span>
                            <span class="picker-label">sec</span>
                            <div class="picker-box-wrapper">
                                <div class="picker-box">
                                    <input type="number" id="focus-m" class="digit-input" min="0" max="180" value="25" oninput="validateDigits(this)">
                                    <span class="picker-colon">:</span>
                                    <input type="number" id="focus-s" class="digit-input" min="0" max="59" value="00" oninput="validateDigits(this)">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- SHORT BREAK COLUMN -->
                <div class="config-column">
                    <div class="column-header">
                        <span class="status-dot short"></span>
                        <h2>Descanso corto</h2>
                    </div>
                    <div class="time-picker">
                        <div class="time-picker-grid">
                            <span class="picker-label">min</span>
                            <span class="picker-separator-label"></span>
                            <span class="picker-label">sec</span>
                            <div class="picker-box-wrapper">
                                <div class="picker-box">
                                    <input type="number" id="short-m" class="digit-input" min="0" max="60" value="05" oninput="validateDigits(this)">
                                    <span class="picker-colon">:</span>
                                    <input type="number" id="short-s" class="digit-input" min="0" max="59" value="00" oninput="validateDigits(this)">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- LONG BREAK COLUMN -->
                <div class="config-column">
                    <div class="long-break-header-row">
                        <div class="column-header">
                            <span class="status-dot long"></span>
                            <h2>Descanso largo</h2>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="long-active" onchange="toggleLongBreakEffect(true)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="time-picker" id="long-break-inputs">
                        <div class="time-picker-grid">
                            <span class="picker-label">min</span>
                            <span class="picker-separator-label"></span>
                            <span class="picker-label">sec</span>
                            <div class="picker-box-wrapper">
                                <div class="picker-box">
                                    <input type="number" id="long-m" class="digit-input" min="0" max="60" value="15" oninput="validateDigits(this)">
                                    <span class="picker-colon">:</span>
                                    <input type="number" id="long-s" class="digit-input" min="0" max="59" value="00" oninput="validateDigits(this)">
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="cycles-container" id="cycles-container">
                        <span class="cycles-label">Ciclos de enfoque requeridos</span>
                        <div class="cycles-input-box">
                            <input type="number" id="long-cycles" min="2" max="99" value="4" oninput="validateDigits(this)">
                        </div>
                    </div>
                </div>
            </div>

            <div class="action-row">
                <button class="btn-save" onclick="guardarConfiguracion()">Guardar configuración</button>
            </div>

            <!-- GUÍA DE GESTOS -->
            <div class="gesture-legend">
                <div class="legend-header">
                    <span class="legend-info-icon">i</span>
                    <span>Guía de gestos del hardware</span>
                </div>
                <div class="legend-list">
                    <div class="legend-item">
                        <span class="legend-cmd">1 clic</span>
                        <span class="legend-desc">Pausar/reanudar la fase (o iniciar desde Standby/Alerta)</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-cmd">2 clics</span>
                        <span class="legend-desc">Reiniciar el tiempo de la fase actual a cero</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-cmd">3 clics</span>
                        <span class="legend-desc">Forzar avance a la siguiente fase (sin parpadeo de alerta)</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-cmd">Mantener 2s</span>
                        <span class="legend-desc">Volver a espera (Standby)</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TOAST NOTIFICACIÓN -->
    <div id="toast" class="toast">Configuración guardada correctamente</div>

    <script>
        // Configurar fuentes globales y colores para Chart.js
        Chart.defaults.font.family = "'Inter', sans-serif";
        Chart.defaults.color = '#8a8f98';
        Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(10, 14, 23, 0.9)';
        Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.08)';
        Chart.defaults.plugins.tooltip.borderWidth = 1;
        Chart.defaults.plugins.tooltip.titleColor = '#ffffff';
        Chart.defaults.plugins.tooltip.bodyColor = '#cbd5e1';

        // Lógica de pestañas (Tabs)
        function switchTab(tabId) {
            document.querySelectorAll('.tab-view').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.menu-item').forEach(btn => btn.classList.remove('active'));
            
            document.getElementById('tab-' + tabId).classList.add('active');
            document.getElementById('btn-' + tabId).classList.add('active');
        }

        // Cargar datos para los gráficos desde el endpoint /api/stats
        async function cargarGraficos() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                // Gráfico de Barras: Minutos por Día
                const ctxDias = document.getElementById('chartDias').getContext('2d');
                new Chart(ctxDias, {
                    type: 'bar',
                    data: {
                        labels: data.dias_labels,
                        sidebar: true,
                        datasets: [{
                            label: 'Minutos de enfoque',
                            data: data.dias_minutos,
                            backgroundColor: 'rgba(224, 90, 90, 0.25)',
                            borderColor: '#e05a5a',
                            borderWidth: 1.5,
                            borderRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { grid: { display: false }, ticks: { color: '#8a8f98' } },
                            y: { grid: { color: 'rgba(255, 255, 255, 0.04)' }, ticks: { color: '#8a8f98' } }
                        }
                    }
                });

                // Gráfico Donut: Distribución de Sesiones
                const ctxTipos = document.getElementById('chartTipos').getContext('2d');
                new Chart(ctxTipos, {
                    type: 'doughnut',
                    data: {
                        labels: ['Enfoque', 'Descanso corto', 'Descanso largo'],
                        datasets: [{
                            data: [data.count_focus, data.count_corto, data.count_largo],
                            backgroundColor: [
                                'rgba(224, 90, 90, 0.85)',
                                'rgba(91, 140, 224, 0.85)',
                                'rgba(82, 190, 144, 0.85)'
                            ],
                            borderWidth: 0
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: { color: '#f3f4f6', boxWidth: 12, padding: 16, font: { size: 12 } }
                            }
                        }
                    }
                });
            } catch(e) {
                console.error("Error cargando estadísticas para los gráficos:", e);
            }
        }

        // Lógica Configuración (dashboard.html)
        function padZero(num) { return num.toString().padStart(2, '0'); }

        function validateDigits(input) {
            let val = input.value;
            if (val.length > 3) input.value = val.slice(0, 3);
            const min = parseInt(input.min) || 0;
            const max = parseInt(input.max) || 999;
            let numericVal = parseInt(input.value);
            if (!isNaN(numericVal)) {
                if (numericVal < min) input.value = min;
                if (numericVal > max) input.value = max;
            }
        }

        function toggleLongBreakEffect(animate = false) {
            const active = document.getElementById('long-active').checked;
            const inputs = document.getElementById('long-break-inputs');
            const cycles = document.getElementById('cycles-container');
            const targetOpacity = active ? '1' : '0.25';
            const targetPointerEvents = active ? 'auto' : 'none';
            if (animate) {
                inputs.style.transition = 'opacity 0.3s';
                cycles.style.transition = 'opacity 0.3s';
            }
            inputs.style.opacity = targetOpacity;
            inputs.style.pointerEvents = targetPointerEvents;
            cycles.style.opacity = targetOpacity;
            cycles.style.pointerEvents = targetPointerEvents;
        }

        // Cargar configuración de tiempos (segundos -> minutos/segundos)
        async function cargarConfiguracion() {
            try {
                const res = await fetch('/api/latest_config');
                const data = await res.json();
                if (data) {
                    document.getElementById('focus-m').value = padZero(Math.floor((data.tiempo_focus || 1500) / 60));
                    document.getElementById('focus-s').value = padZero((data.tiempo_focus || 1500) % 60);
                    document.getElementById('short-m').value = padZero(Math.floor((data.tiempo_descanso_corto || 300) / 60));
                    document.getElementById('short-s').value = padZero((data.tiempo_descanso_corto || 300) % 60);
                    document.getElementById('long-m').value = padZero(Math.floor((data.tiempo_descanso_largo || 900) / 60));
                    document.getElementById('long-s').value = padZero((data.tiempo_descanso_largo || 900) % 60);
                    document.getElementById('long-active').checked = data.descanso_largo_activo !== false;
                    document.getElementById('long-cycles').value = data.ciclos_para_descanso_largo || 4;
                    toggleLongBreakEffect(false);
                }
            } catch(e) {
                console.error("Error cargando configuración inicial:", e);
            }
        }

        // Guardar configuración (minutos/segundos -> segundos)
        async function guardarConfiguracion() {
            const focusM = parseInt(document.getElementById('focus-m').value) || 0;
            const focusS = parseInt(document.getElementById('focus-s').value) || 0;
            const shortM = parseInt(document.getElementById('short-m').value) || 0;
            const shortS = parseInt(document.getElementById('short-s').value) || 0;
            const longM  = parseInt(document.getElementById('long-m').value) || 0;
            const longS  = parseInt(document.getElementById('long-s').value) || 0;
            const totalFocus = focusM * 60 + focusS;
            const totalShort = shortM * 60 + shortS;
            const totalLong  = longM * 60 + longS;
            const longActive = document.getElementById('long-active').checked;
            const longCyclesVal = parseInt(document.getElementById('long-cycles').value) || 4;
            
            if (longActive && longCyclesVal > 99) {
                alert('La cantidad de ciclos para descanso largo no puede ser mayor a 99.');
                return;
            }
            const longCycles = Math.min(99, Math.max(2, longCyclesVal));
            if (totalFocus <= 0 || totalShort <= 0 || (longActive && totalLong <= 0)) {
                alert('Las duraciones de los intervalos deben ser mayores a cero segundos.');
                return;
            }
            
            const payload = {
                tiempo_focus: totalFocus,
                tiempo_descanso_corto: totalShort,
                tiempo_descanso_largo: totalLong,
                ciclos_para_descanso_largo: longCycles,
                descanso_largo_activo: longActive
            };
            
            try {
                const res = await fetch('/api/save_config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await res.json();
                if (result.status === 'success') {
                    const toast = document.getElementById('toast');
                    toast.classList.add('show');
                    setTimeout(() => toast.classList.remove('show'), 3000);
                } else {
                    alert("Error: " + result.message);
                }
            } catch(err) {
                alert("Error de red al guardar.");
            }
        }

        // Formatear ceros al perder foco (onblur)
        const digitInputs = document.querySelectorAll('.digit-input');
        digitInputs.forEach(input => {
            input.addEventListener('blur', () => {
                let val = parseInt(input.value) || 0;
                input.value = padZero(val);
            });
        });

        cargarGraficos();
        cargarConfiguracion();
    </script>
</body>
</html>
"""

def calcular_rachas(conn):
    """Calcula la racha actual y máxima de días consecutivos con al menos 1 sesión Focus"""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date(timestamp) FROM sesiones_pomodoro WHERE tipo_sesion = 'focus' ORDER BY date(timestamp) DESC")
    dias = [datetime.strptime(row[0], '%Y-%m-%d').date() for row in cursor.fetchall()]
    
    if not dias:
        return 0, 0

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    racha_actual = 0
    # Comprobar racha activa desde hoy o ayer
    if today in dias:
        check_date = today
    elif yesterday in dias:
        check_date = yesterday
    else:
        check_date = None

    if check_date:
        for d in dias:
            if d == check_date:
                racha_actual += 1
                check_date -= timedelta(days=1)
            elif d < check_date:
                break

    # Racha máxima histórica
    racha_maxima = 0
    racha_temp = 0
    prev_date = None
    
    for d in sorted(dias):
        if prev_date is None or d == prev_date + timedelta(days=1):
            racha_temp += 1
        else:
            racha_temp = 1
        prev_date = d
        if racha_temp > racha_maxima:
            racha_maxima = racha_temp

    return racha_actual, racha_maxima

@app.route('/', methods=['GET'])
def index():
    """Ruta principal con Dashboard Unificado"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Sesiones de pomodoro (incluyendo flag de avance forzado)
    cursor.execute('SELECT id, timestamp, dispositivo, tipo_sesion, ciclo_num, duracion_s, forzado FROM sesiones_pomodoro ORDER BY id DESC LIMIT 50')
    sesiones = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM sesiones_pomodoro WHERE tipo_sesion = 'focus'")
    total_focus = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(duracion_s), 0) FROM sesiones_pomodoro WHERE tipo_sesion = 'focus'")
    total_segundos_focus = cursor.fetchone()[0]
    total_minutos_focus = round(total_segundos_focus / 60, 1)

    racha_actual, racha_maxima = calcular_rachas(conn)

    # 2. Métricas de Pausas
    cursor.execute("SELECT COUNT(*), COALESCE(AVG(duracion_pausa_s), 0) FROM pausas")
    row_pausas = cursor.fetchone()
    total_pausas = row_pausas[0] if row_pausas else 0
    avg_duracion_pausa = round(row_pausas[1], 1) if row_pausas and row_pausas[1] else 0.0

    cursor.execute("SELECT id, timestamp, fase, tiempo_transcurrido_s, porcentaje_transcurrido, duracion_pausa_s FROM pausas ORDER BY id DESC LIMIT 10")
    ultimas_pausas = cursor.fetchall()

    # 3. Métricas de Reacción
    cursor.execute("SELECT tipo_alerta, COALESCE(AVG(duracion_alerta_s), 0) FROM tiempos_reaccion GROUP BY tipo_alerta")
    reacciones_avg = dict(cursor.fetchall())
    avg_reaccion_focus = round(reacciones_avg.get('POST_FOCUS', 0.0), 2)
    avg_reaccion_corto = round(reacciones_avg.get('POST_DESCANSO_CORTO', 0.0), 2)
    avg_reaccion_largo = round(reacciones_avg.get('POST_DESCANSO_LARGO', 0.0), 2)

    cursor.execute("SELECT id, timestamp, tipo_alerta, duracion_alerta_s FROM tiempos_reaccion ORDER BY id DESC LIMIT 10")
    ultimas_reacciones = cursor.fetchall()

    # 4. Métricas de Avances Forzados / Ciclos
    cursor.execute("SELECT COUNT(*) FROM sesiones_pomodoro WHERE forzado = 1")
    total_forzados = cursor.fetchone()[0]

    cursor.execute("SELECT id, timestamp, fase, evento, tiempo_activo_s, forzado FROM eventos_ciclos ORDER BY id DESC LIMIT 15")
    ultimos_ciclos = cursor.fetchall()

    conn.close()
    
    return render_template_string(
        HTML_DASHBOARD,
        sesiones=sesiones,
        total_focus=total_focus,
        total_minutos_focus=total_minutos_focus,
        racha_actual=racha_actual,
        racha_maxima=racha_maxima,
        total_pausas=total_pausas,
        avg_duracion_pausa=avg_duracion_pausa,
        ultimas_pausas=ultimas_pausas,
        avg_reaccion_focus=avg_reaccion_focus,
        avg_reaccion_corto=avg_reaccion_corto,
        avg_reaccion_largo=avg_reaccion_largo,
        ultimas_reacciones=ultimas_reacciones,
        total_forzados=total_forzados,
        ultimos_ciclos=ultimos_ciclos
    )

def obtener_timestamp_corregido(data):
    """
    Calcula el timestamp real del evento si fue encolado sin sincronización horaria.
    Si se proporciona un timestamp y sync es False, estima la hora exacta a la que ocurrió
    restando la diferencia temporal (current_esp_time - timestamp) al tiempo actual del servidor.
    Retorna el timestamp corregido en formato YYYY-MM-DD HH:MM:SS, o None si no hay timestamp.
    """
    timestamp_str = data.get('timestamp')
    if not timestamp_str:
        return None
        
    if data.get('sync') is False and data.get('current_esp_time'):
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            event_dt = datetime.strptime(timestamp_str, fmt)
            esp_current_dt = datetime.strptime(data['current_esp_time'], fmt)
            
            # Diferencia en segundos entre el momento del evento y el momento de envío
            diff_seconds = (esp_current_dt - event_dt).total_seconds()
            if diff_seconds < 0:
                diff_seconds = 0
                
            # El timestamp real es el tiempo actual del servidor (UTC) menos esa diferencia
            real_dt = datetime.utcnow() - timedelta(seconds=diff_seconds)
            return real_dt.strftime(fmt)
        except Exception as e:
            print("[TIME CORRECTION ERROR] Error calculando tiempo corregido:", e)
            
    return timestamp_str

@app.route('/datos', methods=['POST'])
def recibir_datos():
    """Endpoint POST para recibir eventos desde la ESP32"""
    try:
        data = request.get_json(force=True)
        dispositivo = data.get('dispositivo', 'ESP32_Pomodoro')
        tipo_sesion = data.get('tipo_sesion', 'focus')
        ciclo_num = data.get('ciclo_num', 1)
        duracion_s = data.get('duracion_s', 0)
        forzado = int(data.get('forzado', 0))
        
        # Mapeo de compatibilidad con payload previo
        if data.get('evento') == 'ciclo_rojo_completado':
            tipo_sesion = 'focus'
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener el ID de la configuración activa
        cursor.execute("SELECT id FROM configuraciones ORDER BY id DESC LIMIT 1")
        config_row = cursor.fetchone()
        config_id = config_row[0] if config_row else None
        
        timestamp = obtener_timestamp_corregido(data)
        if timestamp:
            cursor.execute('''
                INSERT INTO sesiones_pomodoro (timestamp, dispositivo, tipo_sesion, ciclo_num, duracion_s, configuracion_id, forzado)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, dispositivo, tipo_sesion, ciclo_num, duracion_s, config_id, forzado))
        else:
            cursor.execute('''
                INSERT INTO sesiones_pomodoro (dispositivo, tipo_sesion, ciclo_num, duracion_s, configuracion_id, forzado)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (dispositivo, tipo_sesion, ciclo_num, duracion_s, config_id, forzado))
        conn.commit()
        conn.close()
        
        print(f"[BD FLASK] Sesión '{tipo_sesion}' guardada: Ciclo #{ciclo_num} ({duracion_s}s), Config ID: {config_id}, Forzado: {forzado}, Timestamp: {timestamp}")
        return jsonify({"status": "success", "message": "Sesión registrada en la BD"}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Error procesando POST:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/registro_pausa', methods=['POST'])
def registro_pausa():
    try:
        data = request.get_json(force=True)
        fase = data.get('fase', 'DESCONOCIDO')
        tiempo_transcurrido_s = int(data.get('tiempo_transcurrido_s', 0))
        porcentaje_transcurrido = float(data.get('porcentaje_transcurrido', 0.0))
        duracion_pausa_s = int(data.get('duracion_pausa_s', 0))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener el ID de la configuración activa
        cursor.execute("SELECT id FROM configuraciones ORDER BY id DESC LIMIT 1")
        config_row = cursor.fetchone()
        config_id = config_row[0] if config_row else None
        
        timestamp = obtener_timestamp_corregido(data)
        if timestamp:
            cursor.execute('''
                INSERT INTO pausas (timestamp, fase, tiempo_transcurrido_s, porcentaje_transcurrido, duracion_pausa_s, configuracion_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (timestamp, fase, tiempo_transcurrido_s, porcentaje_transcurrido, duracion_pausa_s, config_id))
        else:
            cursor.execute('''
                INSERT INTO pausas (fase, tiempo_transcurrido_s, porcentaje_transcurrido, duracion_pausa_s, configuracion_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (fase, tiempo_transcurrido_s, porcentaje_transcurrido, duracion_pausa_s, config_id))
        conn.commit()
        conn.close()
        
        print(f"[BD FLASK] Pausa registrada: Fase {fase}, Transcurrido {tiempo_transcurrido_s}s ({porcentaje_transcurrido}%), Duración {duracion_pausa_s}s, Config ID: {config_id}, Timestamp: {timestamp}")
        return jsonify({"status": "success", "message": "Pausa registrada"}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Error en registro_pausa:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/registro_reaccion', methods=['POST'])
def registro_reaccion():
    try:
        data = request.get_json(force=True)
        tipo_alerta = data.get('tipo_alerta', 'DESCONOCIDO')
        duracion_alerta_s = float(data.get('duracion_alerta_s', 0.0))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener el ID de la configuración activa
        cursor.execute("SELECT id FROM configuraciones ORDER BY id DESC LIMIT 1")
        config_row = cursor.fetchone()
        config_id = config_row[0] if config_row else None
        
        timestamp = obtener_timestamp_corregido(data)
        if timestamp:
            cursor.execute('''
                INSERT INTO tiempos_reaccion (timestamp, tipo_alerta, duracion_alerta_s, configuracion_id)
                VALUES (?, ?, ?, ?)
            ''', (timestamp, tipo_alerta, duracion_alerta_s, config_id))
        else:
            cursor.execute('''
                INSERT INTO tiempos_reaccion (tipo_alerta, duracion_alerta_s, configuracion_id)
                VALUES (?, ?, ?)
            ''', (tipo_alerta, duracion_alerta_s, config_id))
        conn.commit()
        conn.close()
        
        print(f"[BD FLASK] Reacción registrada: Alerta {tipo_alerta}, Reacción {duracion_alerta_s}s, Config ID: {config_id}, Timestamp: {timestamp}")
        return jsonify({"status": "success", "message": "Reacción registrada"}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Error en registro_reaccion:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/registro_ciclo', methods=['POST'])
def registro_ciclo():
    try:
        data = request.get_json(force=True)
        fase = data.get('fase', 'DESCONOCIDO')
        evento = data.get('evento', 'DESCONOCIDO')
        tiempo_activo_s = int(data.get('tiempo_activo_s', 0))
        forzado = int(data.get('forzado', 0))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener el ID de la configuración activa
        cursor.execute("SELECT id FROM configuraciones ORDER BY id DESC LIMIT 1")
        config_row = cursor.fetchone()
        config_id = config_row[0] if config_row else None
        
        timestamp = obtener_timestamp_corregido(data)
        if timestamp:
            cursor.execute('''
                INSERT INTO eventos_ciclos (timestamp, fase, evento, tiempo_activo_s, configuracion_id, forzado)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (timestamp, fase, evento, tiempo_activo_s, config_id, forzado))
        else:
            cursor.execute('''
                INSERT INTO eventos_ciclos (fase, evento, tiempo_activo_s, configuracion_id, forzado)
                VALUES (?, ?, ?, ?, ?)
            ''', (fase, evento, tiempo_activo_s, config_id, forzado))
        conn.commit()
        conn.close()
        
        print(f"[BD FLASK] Evento de ciclo registrado: Fase {fase}, Evento {evento}, Tiempo activo {tiempo_activo_s}s, Config ID: {config_id}, Forzado: {forzado}, Timestamp: {timestamp}")
        return jsonify({"status": "success", "message": "Evento de ciclo registrado"}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Error en registro_ciclo:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """API JSON para proveer estadísticas a los gráficos interactivos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Conteo por tipo de sesión
    cursor.execute("SELECT tipo_sesion, COUNT(*) FROM sesiones_pomodoro GROUP BY tipo_sesion")
    counts = dict(cursor.fetchall())
    
    # Focus acumulado por día en los últimos 7 días
    cursor.execute("""
        SELECT date(timestamp) as dia, SUM(duracion_s) / 60.0
        FROM sesiones_pomodoro
        WHERE tipo_sesion = 'focus' AND timestamp >= date('now', '-6 days')
        GROUP BY date(timestamp)
        ORDER BY dia ASC
    """)
    dias_data = cursor.fetchall()
    conn.close()
    
    dias_labels = [row[0] for row in dias_data]
    dias_minutos = [round(row[1], 1) for row in dias_data]
    
    return jsonify({
        "count_focus": counts.get('focus', 0),
        "count_corto": counts.get('descanso_corto', 0),
        "count_largo": counts.get('descanso_largo', 0),
        "dias_labels": dias_labels,
        "dias_minutos": dias_minutos
    })

@app.route('/api/save_config', methods=['POST'])
def save_config():
    """Endpoint para guardar la configuración en la base de datos (evita duplicados idénticos)"""
    try:
        data = request.get_json(force=True)
        tiempo_focus = int(data.get('tiempo_focus', 1500))
        tiempo_descanso_corto = int(data.get('tiempo_descanso_corto', 300))
        tiempo_descanso_largo = int(data.get('tiempo_descanso_largo', 900))
        descanso_largo_activo = 1 if data.get('descanso_largo_activo', True) else 0
        ciclos_para_descanso_largo = int(data.get('ciclos_para_descanso_largo', 4))
        if descanso_largo_activo == 1 and ciclos_para_descanso_largo > 99:
            return jsonify({"status": "error", "message": "La cantidad de ciclos para descanso largo no puede ser mayor a 99"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Consultar la configuración más reciente para ver si cambió
        cursor.execute('''
            SELECT tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo 
            FROM configuraciones ORDER BY id DESC LIMIT 1
        ''')
        row = cursor.fetchone()
        
        if (not row or 
            row[0] != tiempo_focus or 
            row[1] != tiempo_descanso_corto or 
            row[2] != tiempo_descanso_largo or 
            row[3] != descanso_largo_activo or 
            row[4] != ciclos_para_descanso_largo):
            
            cursor.execute('''
                INSERT INTO configuraciones (tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo)
                VALUES (?, ?, ?, ?, ?)
            ''', (tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo))
            conn.commit()
            print("[BD FLASK] Nueva configuración de tiempos guardada en base de datos.")
            message = "Configuración registrada en la BD (Nueva fila)"
        else:
            print("[BD FLASK] La configuración es idéntica a la anterior. No se crea una nueva fila.")
            message = "Configuración idéntica, no se requiere inserción"
            
        conn.close()
        return jsonify({"status": "success", "message": message}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Fallo al guardar configuración:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/latest_config', methods=['GET'])
def latest_config():
    """Endpoint para proveer la última configuración registrada en la base de datos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo FROM configuraciones ORDER BY id DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        
        now_utc = datetime.utcnow()
        # Enviar la tupla de tiempo UTC para que la ESP32 sincronice su RTC directamente
        server_time = [now_utc.year, now_utc.month, now_utc.day, now_utc.weekday(), now_utc.hour, now_utc.minute, now_utc.second, 0]
        
        if row:
            return jsonify({
                "tiempo_focus": row[0],
                "tiempo_descanso_corto": row[1],
                "tiempo_descanso_largo": row[2],
                "descanso_largo_activo": bool(row[3]),
                "ciclos_para_descanso_largo": row[4],
                "server_time": server_time
            }), 200
        else:
            return jsonify({
                "server_time": server_time
            }), 200
    except Exception as e:
        print("[BD FLASK ERROR] Fallo al leer última configuración:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/ota/manifest', methods=['GET'])
def ota_manifest():
    """Genera la lista de archivos Python y sus respectivos hashes SHA-256"""
    try:
        import os
        import hashlib
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        files_manifest = {}
        for filename in os.listdir(root_dir):
            if filename.endswith('.py') and not filename.startswith('.'):
                file_path = os.path.join(root_dir, filename)
                if os.path.isfile(file_path):
                    sha256_hash = hashlib.sha256()
                    with open(file_path, "rb") as f:
                        for byte_block in iter(lambda: f.read(4096), b""):
                            sha256_hash.update(byte_block)
                    files_manifest[filename] = sha256_hash.hexdigest()
        return jsonify({"files": files_manifest}), 200
    except Exception as e:
        print("[OTA ERROR] Fallo al generar manifest:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/ota/download/<filename>', methods=['GET'])
def ota_download(filename):
    """Descarga de manera segura un archivo Python del directorio raíz"""
    try:
        import os
        if '/' in filename or '\\' in filename or filename.startswith('.'):
            return "Acceso denegado", 403
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        file_path = os.path.join(root_dir, filename)
        if not filename.endswith('.py') or not os.path.isfile(file_path):
            return "Archivo no encontrado", 404
        from flask import send_file
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        print(f"[OTA ERROR] Fallo al descargar archivo {filename}:", e)
        return "Error interno del servidor", 500

def run_mqtt_listener():
    """Hilo secundario para conectarse al Broker MQTT y recibir reportes de sesión de la ESP32"""
    import paho.mqtt.client as mqtt
    
    def on_connect(client, userdata, flags, rc):
        print(f"[MQTT CLIENT] Conectado al Broker con código de resultado: {rc}", flush=True)
        client.subscribe("pomodoro/sesiones")
        print("[MQTT CLIENT] Suscrito a 'pomodoro/sesiones'", flush=True)

    def on_message(client, userdata, message):
        try:
            payload = message.payload.decode("utf-8")
            print(f"[MQTT MESSAGE] Recibido payload: {payload}", flush=True)
            data = json.loads(payload)
            
            dispositivo = data.get('dispositivo', 'ESP32_Pomodoro')
            tipo_sesion = data.get('tipo_sesion', 'focus')
            ciclo_num = int(data.get('ciclo_num', 1))
            duracion_s = int(data.get('duracion_s', 0))
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sesiones_pomodoro (dispositivo, tipo_sesion, ciclo_num, duracion_s)
                VALUES (?, ?, ?, ?)
            ''', (dispositivo, tipo_sesion, ciclo_num, duracion_s))
            conn.commit()
            conn.close()
            print(f"[SQLITE MQTT] Guardada sesión de {tipo_sesion} #{ciclo_num} ({duracion_s}s) desde MQTT", flush=True)
        except Exception as e:
            print("[MQTT LISTENER ERROR] Error procesando mensaje MQTT:", e, flush=True)

    try:
        # Intentar paho-mqtt v2, si no v1 (compatibilidad)
        try:
            client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
        except AttributeError:
            client = mqtt.Client()
            
        client.on_connect = on_connect
        client.on_message = on_message
        
        print("[MQTT LISTENER] Conectando a broker.hivemq.com:1883...", flush=True)
        client.connect("broker.hivemq.com", 1883, 60)
        client.loop_forever()
    except Exception as e:
        print("[MQTT LISTENER ERROR] Fallo en cliente MQTT:", e, flush=True)

def run_udp_discovery():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Reutilizar puerto para evitar errores de Bind en reinicios rápidos
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', 5002))
        print("[UDP DISCOVERY] Servidor de descubrimiento escuchando en puerto 5002...", flush=True)
        while True:
            data, addr = sock.recvfrom(1024)
            if data == b"POMODORO_DISCOVER":
                # Respondemos con la firma y el puerto del servidor Flask
                sock.sendto(b"POMODORO_RESPONSE:5001", addr)
                print(f"[UDP DISCOVERY] Respondido descubrimiento a {addr}", flush=True)
    except Exception as e:
        print("[UDP DISCOVERY ERROR] Fallo en servidor UDP:", e, flush=True)
    finally:
        sock.close()

if __name__ == '__main__':
    # Configuración de debug activa
    debug_mode = True
    
    # Iniciar escuchador MQTT y servidor de descubrimiento UDP en segundo plano solo en el proceso activo (evita duplicación por el auto-reloader de Flask)
    if not debug_mode or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=run_mqtt_listener, daemon=True).start()
        threading.Thread(target=run_udp_discovery, daemon=True).start()

    print("\n=======================================================")
    print(" SERVIDOR FLASK ANALYTICS PRO INICIADO EN PC")
    print(" URL Local Dashboard: http://localhost:5001")
    print(" URL Endpoint ESP32: Dinámico (Autodescubrimiento activo en puerto 5002)")
    print(" Base de Datos SQLite: pomodoro.db")
    print("=======================================================\n")
    app.run(host='0.0.0.0', port=5001, debug=debug_mode)
