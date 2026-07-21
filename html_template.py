# --- PLANTILLA HTML SIMPLIFICADA SERVIDA DESDE LA ESP32 ---
HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuración Pomodoro ESP32</title>
    <style>
        :root {
            --bg: #0f172a;
            --card-bg: #1e293b;
            --primary: #3b82f6;
            --red: #ef4444;
            --blue: #3b82f6;
            --text: #f8fafc;
            --font: system-ui, -apple-system, sans-serif;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: var(--font);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .card {
            width: 100%;
            max-width: 400px;
            background: var(--card-bg);
            border-radius: 16px;
            padding: 28px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        }
        h2 { font-size: 1.4rem; font-weight: 700; margin-bottom: 20px; text-align: center; color: #fff; }
        .form-group { margin-bottom: 20px; }
        label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 8px; color: #cbd5e1; }
        .label-red { color: #f87171; }
        .label-blue { color: #60a5fa; }
        .input-wrapper { display: flex; align-items: center; position: relative; }
        input[type="number"] {
            width: 100%;
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 12px 14px;
            color: #fff;
            font-size: 1.1rem;
            outline: none;
            transition: border-color 0.2s;
        }
        input[type="number"]:focus { border-color: var(--primary); }
        .unit { position: absolute; right: 14px; color: #64748b; font-size: 0.9rem; pointer-events: none; }
        button {
            width: 100%;
            background: var(--primary);
            border: none;
            border-radius: 10px;
            padding: 14px;
            font-weight: 700;
            font-size: 1rem;
            color: #fff;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
            margin-top: 10px;
        }
        button:hover { background: #2563eb; }
        button:active { transform: scale(0.98); }
        .msg {
            margin-top: 16px;
            font-size: 0.85rem;
            text-align: center;
            padding: 10px;
            border-radius: 8px;
            display: none;
        }
        .msg-success { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    </style>
</head>
<body>
    <div class="card">
        <h2>Configurar Duración LEDs</h2>
        
        <div class="form-group">
            <label for="rojo-input" class="label-red">Duración LED Rojo (Segundos)</label>
            <div class="input-wrapper">
                <input type="number" id="rojo-input" min="1" max="3600" value="5">
                <span class="unit">seg</span>
            </div>
        </div>

        <div class="form-group">
            <label for="azul-input" class="label-blue">Duración LED Azul (Segundos)</label>
            <div class="input-wrapper">
                <input type="number" id="azul-input" min="1" max="3600" value="3">
                <span class="unit">seg</span>
            </div>
        </div>

        <button onclick="guardarConfig()">Guardar Tiempos</button>
        <div id="msg" class="msg msg-success">¡Tiempos guardados correctamente!</div>
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
                const msg = document.getElementById('msg');
                msg.style.display = 'block';
                setTimeout(() => msg.style.display = 'none', 3000);
            } catch(e) {
                alert('Error al comunicar con la ESP32.');
            }
        }

        cargarConfig();
    </script>
</body>
</html>
"""
