# --- PLANTILLA HTML SERVIDA DESDE LA ESP32 ---
HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32 Pomodoro Server</title>
    <style>
        :root {
            --bg: #090d16;
            --card-bg: rgba(22, 30, 46, 0.75);
            --border: rgba(255, 255, 255, 0.1);
            --red: #ff3b30;
            --blue: #007aff;
            --yellow: #ffcc00;
            --font: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: #f1f5f9;
            font-family: var(--font);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            width: 100%;
            max-width: 440px;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 32px 24px;
            box-shadow: 0 20px 50px rgba(0,0,0,0.6);
            text-align: center;
        }
        h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 4px; color: #fff; }
        .subtitle { font-size: 0.85rem; color: #94a3b8; margin-bottom: 28px; }
        .badge {
            display: inline-block;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 1px;
            margin-bottom: 16px;
            text-transform: uppercase;
            background: rgba(255, 255, 255, 0.08);
        }
        .badge.AMARILLO { color: var(--yellow); background: rgba(255, 204, 0, 0.15); border: 1px solid rgba(255, 204, 0, 0.3); }
        .badge.ROJO { color: var(--red); background: rgba(255, 59, 48, 0.15); border: 1px solid rgba(255, 59, 48, 0.3); }
        .badge.AZUL { color: var(--blue); background: rgba(0, 122, 255, 0.15); border: 1px solid rgba(0, 122, 255, 0.3); }
        .badge.ALERTA { color: #f43f5e; background: rgba(244, 63, 94, 0.2); border: 1px solid rgba(244, 63, 94, 0.4); animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        
        .timer-display {
            font-size: 3.8rem;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 24px;
            font-variant-numeric: tabular-nums;
        }
        .card {
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px;
            margin-top: 10px;
            text-align: left;
        }
        .input-group { margin-bottom: 16px; }
        label { display: block; font-size: 0.8rem; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; text-transform: uppercase; }
        .input-wrapper { display: flex; align-items: center; position: relative; }
        input[type="number"] {
            width: 100%;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            padding: 12px 14px;
            color: #fff;
            font-size: 1rem;
            outline: none;
        }
        input[type="number"]:focus { border-color: var(--blue); }
        .unit { position: absolute; right: 14px; color: #64748b; font-size: 0.85rem; }
        button {
            width: 100%;
            background: linear-gradient(135deg, #007aff 0%, #0056b3 100%);
            border: none;
            border-radius: 10px;
            padding: 14px;
            font-weight: 700;
            font-size: 0.95rem;
            color: #fff;
            cursor: pointer;
            transition: transform 0.1s ease;
        }
        button:active { transform: scale(0.98); }
        .toast {
            margin-top: 14px;
            font-size: 0.85rem;
            color: #10b981;
            text-align: center;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Pomodoro ESP32</h1>
        <p class="subtitle">Servidor HTTP embebido</p>

        <div id="badge-estado" class="badge AMARILLO">AMARILLO</div>
        <div id="time-display" class="timer-display">0s</div>

        <div class="card">
            <div class="input-group">
                <label for="rojo-input">Tiempo LED Rojo (Pomodoro / Trabajo)</label>
                <div class="input-wrapper">
                    <input type="number" id="rojo-input" min="1" max="3600" value="5">
                    <span class="unit">seg</span>
                </div>
            </div>
            <div class="input-group">
                <label for="azul-input">Tiempo LED Azul (Descanso)</label>
                <div class="input-wrapper">
                    <input type="number" id="azul-input" min="1" max="3600" value="3">
                    <span class="unit">seg</span>
                </div>
            </div>
            <button onclick="guardarConfig()">Guardar Configuración</button>
            <div id="toast" class="toast">¡Configuración guardada correctamente!</div>
        </div>
    </div>

    <script>
        async function cargarConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                if (data.tiempo_rojo) document.getElementById('rojo-input').value = data.tiempo_rojo;
                if (data.tiempo_azul) document.getElementById('azul-input').value = data.tiempo_azul;
            } catch(e) {}
        }

        async function guardarConfig() {
            const rojo = parseInt(document.getElementById('rojo-input').value);
            const azul = parseInt(document.getElementById('azul-input').value);
            if (isNaN(rojo) || rojo <= 0 || isNaN(azul) || azul <= 0) {
                alert('Por favor ingrese valores mayores a 0.');
                return;
            }
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tiempo_rojo: rojo, tiempo_azul: azul })
                });
                const toast = document.getElementById('toast');
                toast.style.display = 'block';
                setTimeout(() => toast.style.display = 'none', 3000);
            } catch(e) {
                alert('Error al comunicar con la ESP32.');
            }
        }

        async function pollingEstado() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                const badge = document.getElementById('badge-estado');
                badge.className = 'badge ' + data.estado_nombre;
                badge.innerText = data.estado_nombre;
                
                if (data.estado_nombre === 'ROJO' || data.estado_nombre === 'AZUL') {
                    document.getElementById('time-display').innerText = data.remaining_s + 's';
                } else {
                    document.getElementById('time-display').innerText = '0s';
                }
            } catch(e) {}
        }

        cargarConfig();
        setInterval(pollingEstado, 400);
    </script>
</body>
</html>
"""
