import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'pomodoro.db')

def init_db():
    """Inicializa la base de datos SQLite y crea la tabla de ciclos si no existe"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ciclos_rojos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            dispositivo TEXT,
            ciclo_num INTEGER,
            duracion_s INTEGER
        )
    ''')
    conn.commit()
    conn.close()

# Inicializar BD al arrancar la app
init_db()

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Servidor Flask - Registro Pomodoro ESP32</title>
    <style>
        :root {
            --bg: #090d16;
            --card-bg: #161e2e;
            --primary: #ef4444;
            --text: #f1f5f9;
            --border: rgba(255, 255, 255, 0.1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: system-ui, -apple-system, sans-serif;
            padding: 40px 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        h1 { font-size: 2rem; color: #fff; margin-bottom: 8px; }
        p { color: #94a3b8; font-size: 0.95rem; }
        .stats-card {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(220, 38, 38, 0.05) 100%);
            border: 1px solid rgba(239, 68, 68, 0.4);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
            margin-bottom: 30px;
        }
        .stat-value { font-size: 3.5rem; font-weight: 800; color: #ef4444; line-height: 1; }
        .stat-label { font-size: 0.9rem; font-weight: 700; color: #fca5a5; text-transform: uppercase; margin-top: 8px; }
        
        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--card-bg);
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid var(--border);
        }
        th, td {
            padding: 16px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th { background: rgba(255, 255, 255, 0.05); color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; }
        tr:hover { background: rgba(255, 255, 255, 0.02); }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
            font-weight: 700;
            font-size: 0.8rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Servidor Flask - Registro Pomodoro</h1>
            <p>Monitoreo de ciclos de LED Rojo recibidos desde el ESP32</p>
        </div>

        <div class="stats-card">
            <div class="stat-value">{{ total_ciclos }}</div>
            <div class="stat-label">Ciclos Rojos Completados en BD</div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Fecha y Hora</th>
                    <th>Dispositivo</th>
                    <th>Nº Ciclo</th>
                    <th>Duración (seg)</th>
                </tr>
            </thead>
            <tbody>
                {% for fila in registros %}
                <tr>
                    <td>#{{ fila[0] }}</td>
                    <td>{{ fila[1] }}</td>
                    <td><span class="badge">{{ fila[2] }}</span></td>
                    <td>Ciclo {{ fila[3] }}</td>
                    <td>{{ fila[4] }} s</td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="5" style="text-align: center; color: #64748b; padding: 30px;">
                        No hay registros guardados aún. Inicia un ciclo rojo en tu ESP32.
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    """Ruta principal que muestra el Dashboard en la PC"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, timestamp, dispositivo, ciclo_num, duracion_s FROM ciclos_rojos ORDER BY id DESC')
    registros = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) FROM ciclos_rojos')
    total_ciclos = cursor.fetchone()[0]
    conn.close()
    
    return render_template_string(HTML_DASHBOARD, registros=registros, total_ciclos=total_ciclos)

@app.route('/datos', methods=['POST'])
def recibir_datos():
    """Ruta /datos que recibe el evento POST desde la ESP32 y guarda en SQLite"""
    try:
        data = request.get_json(force=True)
        dispositivo = data.get('dispositivo', 'ESP32')
        ciclo_num = data.get('ciclo_num', 1)
        duracion_s = data.get('duracion_s', 0)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ciclos_rojos (dispositivo, ciclo_num, duracion_s)
            VALUES (?, ?, ?)
        ''', (dispositivo, ciclo_num, duracion_s))
        conn.commit()
        conn.close()
        
        print(f"[BD FLASK] Registro guardado correctamente: Ciclo {ciclo_num} ({duracion_s}s)")
        return jsonify({"status": "success", "message": "Ciclo rojo registrado en la BD"}), 200
    except Exception as e:
        print("[BD FLASK ERROR] Error al guardar en BD:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/ciclos', methods=['GET'])
def api_ciclos():
    """API JSON para consultar los ciclos guardados"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, timestamp, dispositivo, ciclo_num, duracion_s FROM ciclos_rojos ORDER BY id DESC')
    filas = cursor.fetchall()
    conn.close()
    
    lista = []
    for f in filas:
        lista.append({
            "id": f[0],
            "timestamp": f[1],
            "dispositivo": f[2],
            "ciclo_num": f[3],
            "duracion_s": f[4]
        })
    return jsonify(lista)

if __name__ == '__main__':
    print("\n=======================================================")
    print(" SERVIDOR FLASK INICIADO EN PC")
    print(" URL Local: http://localhost:5001")
    print(" URL para ESP32: http://192.168.0.125:5001/datos")
    print(" Base de Datos: pomodoro.db")
    print("=======================================================\n")
    app.run(host='0.0.0.0', port=5001, debug=True)
