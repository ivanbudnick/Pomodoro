import os
import sqlite3
import threading
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'pomodoro.db')

def init_db():
    """Inicializa la base de datos SQLite con soporte para tipos de sesión Pomodoro Pro"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Crear tabla de sesiones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sesiones_pomodoro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            dispositivo TEXT,
            tipo_sesion TEXT DEFAULT 'focus',
            ciclo_num INTEGER,
            duracion_s INTEGER
        )
    ''')
    
    # Crear tabla de configuraciones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuraciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            tiempo_focus INTEGER,
            tiempo_descanso_corto INTEGER,
            tiempo_descanso_largo INTEGER,
            descanso_largo_activo INTEGER,
            ciclos_para_descanso_largo INTEGER
        )
    ''')
    
    # Migrar tabla legacy si existía
    cursor.execute("PRAGMA table_info(ciclos_rojos)")
    legacy_exists = cursor.fetchall()
    if legacy_exists:
        try:
            cursor.execute('''
                INSERT INTO sesiones_pomodoro (timestamp, dispositivo, tipo_sesion, ciclo_num, duracion_s)
                SELECT timestamp, dispositivo, 'focus', ciclo_num, duracion_s FROM ciclos_rojos
            ''')
            cursor.execute("DROP TABLE ciclos_rojos")
        except:
            pass
            
    conn.commit()
    conn.close()

init_db()

# --- PLANTILLA DASHBOARD CON ESTÉTICA UNIFICADA Y CHART.JS ---
HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pomodoro esp32 - Panel de estadísticas</title>
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
            padding: 40px 24px;
        }

        .container {
            width: 100%;
            max-width: 1300px;
            margin: 0 auto;
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
    </style>
</head>
<body>
    <div class="container">
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
                        <td>{{ s[5] }} seg</td>
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
    </div>

    <script>
        // Configurar fuentes globales y colores para Chart.js
        Chart.defaults.font.family = "'Inter', sans-serif";
        Chart.defaults.color = '#8a8f98';
        Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(10, 14, 23, 0.9)';
        Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.08)';
        Chart.defaults.plugins.tooltip.borderWidth = 1;
        Chart.defaults.plugins.tooltip.titleColor = '#ffffff';
        Chart.defaults.plugins.tooltip.bodyColor = '#cbd5e1';

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

        cargarGraficos();
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, timestamp, dispositivo, tipo_sesion, ciclo_num, duracion_s FROM sesiones_pomodoro ORDER BY id DESC LIMIT 50')
    sesiones = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM sesiones_pomodoro WHERE tipo_sesion = 'focus'")
    total_focus = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(duracion_s), 0) FROM sesiones_pomodoro WHERE tipo_sesion = 'focus'")
    total_segundos_focus = cursor.fetchone()[0]
    total_minutos_focus = round(total_segundos_focus / 60, 1)

    racha_actual, racha_maxima = calcular_rachas(conn)
    conn.close()
    
    return render_template_string(
        HTML_DASHBOARD,
        sesiones=sesiones,
        total_focus=total_focus,
        total_minutos_focus=total_minutos_focus,
        racha_actual=racha_actual,
        racha_maxima=racha_maxima
    )

@app.route('/datos', methods=['POST'])
def recibir_datos():
    """Endpoint POST para recibir eventos desde la ESP32"""
    try:
        data = request.get_json(force=True)
        dispositivo = data.get('dispositivo', 'ESP32_Pomodoro')
        tipo_sesion = data.get('tipo_sesion', 'focus')
        ciclo_num = data.get('ciclo_num', 1)
        duracion_s = data.get('duracion_s', 0)
        
        # Mapeo de compatibilidad con payload previo
        if data.get('evento') == 'ciclo_rojo_completado':
            tipo_sesion = 'focus'
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sesiones_pomodoro (dispositivo, tipo_sesion, ciclo_num, duracion_s)
            VALUES (?, ?, ?, ?)
        ''', (dispositivo, tipo_sesion, ciclo_num, duracion_s))
        conn.commit()
        conn.close()
        
        print(f"[BD FLASK] Sesión '{tipo_sesion}' guardada: Ciclo #{ciclo_num} ({duracion_s}s)")
        return jsonify({"status": "success", "message": "Sesión registrada en la BD"}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Error procesando POST:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """API JSON para proveer estadísticas a los gráficos interactivos"""
    conn = sqlite3.connect(DB_PATH)
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
    """Endpoint para guardar la última configuración configurada en la base de datos"""
    try:
        data = request.get_json(force=True)
        tiempo_focus = int(data.get('tiempo_focus', 1500))
        tiempo_descanso_corto = int(data.get('tiempo_descanso_corto', 300))
        tiempo_descanso_largo = int(data.get('tiempo_descanso_largo', 900))
        descanso_largo_activo = 1 if data.get('descanso_largo_activo', True) else 0
        ciclos_para_descanso_largo = int(data.get('ciclos_para_descanso_largo', 4))
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO configuraciones (tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo)
            VALUES (?, ?, ?, ?, ?)
        ''', (tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo))
        conn.commit()
        conn.close()
        
        print("[BD FLASK] Nueva configuración de tiempos guardada en base de datos.")
        return jsonify({"status": "success", "message": "Configuración registrada en la BD"}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Fallo al guardar configuración:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/latest_config', methods=['GET'])
def latest_config():
    """Endpoint para proveer la última configuración registrada en la base de datos"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo FROM configuraciones ORDER BY id DESC LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                "tiempo_focus": row[0],
                "tiempo_descanso_corto": row[1],
                "tiempo_descanso_largo": row[2],
                "descanso_largo_activo": bool(row[3]),
                "ciclos_para_descanso_largo": row[4]
            }), 200
        else:
            return jsonify({}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Fallo al leer última configuración:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

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
            
            conn = sqlite3.connect(DB_PATH)
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

# Iniciar escuchador MQTT en segundo plano
threading.Thread(target=run_mqtt_listener, daemon=True).start()

if __name__ == '__main__':
    print("\n=======================================================")
    print(" SERVIDOR FLASK ANALYTICS PRO INICIADO EN PC")
    print(" URL Local Dashboard: http://localhost:5001")
    print(" URL Endpoint ESP32: http://192.168.0.125:5001/datos")
    print(" Base de Datos SQLite: pomodoro.db")
    print("=======================================================\n")
    app.run(host='0.0.0.0', port=5001, debug=True)
