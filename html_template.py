# --- PLANTILLA HTML UNIFICADA SERVIDA DESDE LA ESP32 ---
HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pomodoro ESP32 Pro - Configuración</title>
    <style>
        :root {
            --bg: #090d16;
            --card-bg: rgba(22, 30, 46, 0.8);
            --border: rgba(255, 255, 255, 0.1);
            --focus: #ef4444;
            --descanso-corto: #3b82f6;
            --descanso-largo: #10b981;
            --text: #f8fafc;
            --muted: #94a3b8;
            --font: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
            padding: 24px 16px;
        }
        .container {
            width: 100%;
            max-width: 480px;
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 32px 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
        }
        .header {
            text-align: center;
            margin-bottom: 28px;
        }
        .logo-tag {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            background: rgba(59, 130, 246, 0.15);
            border: 1px solid rgba(59, 130, 246, 0.3);
            color: #60a5fa;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        h1 { font-size: 1.6rem; font-weight: 800; color: #fff; margin-bottom: 4px; }
        .subtitle { font-size: 0.85rem; color: var(--muted); }
        
        .section-title {
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section-title.focus { color: var(--focus); }
        .section-title.short { color: var(--descanso-corto); }
        .section-title.long { color: var(--descanso-largo); }
        
        .time-inputs {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 20px;
        }
        .input-box {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 10px 14px;
        }
        .input-box label {
            display: block;
            font-size: 0.7rem;
            font-weight: 600;
            color: var(--muted);
            margin-bottom: 4px;
            text-transform: uppercase;
        }
        .input-box input {
            width: 100%;
            background: transparent;
            border: none;
            color: #fff;
            font-size: 1.1rem;
            font-weight: 700;
            outline: none;
        }

        .card-option {
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 20px;
        }
        .toggle-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }
        .toggle-label {
            font-size: 0.9rem;
            font-weight: 600;
            color: #fff;
        }
        
        /* Switch Custom Toggle */
        .switch {
            position: relative;
            display: inline-block;
            width: 48px;
            height: 26px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #334155;
            transition: .3s;
            border-radius: 26px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 20px; width: 20px;
            left: 3px; bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--descanso-largo); }
        input:checked + .slider:before { transform: translateX(22px); }

        button.btn-save {
            width: 100%;
            background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
            border: none;
            border-radius: 14px;
            padding: 16px;
            font-weight: 700;
            font-size: 1rem;
            color: #fff;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
            transition: transform 0.1s, background 0.2s;
            margin-bottom: 24px;
        }
        button.btn-save:active { transform: scale(0.98); }

        /* INSTRUCTIVO VISUAL DEL BOTÓN */
        .manual-card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px dashed rgba(255, 255, 255, 0.15);
            border-radius: 18px;
            padding: 18px;
        }
        .manual-title {
            font-size: 0.85rem;
            font-weight: 700;
            color: #fff;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .manual-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
        }
        .manual-item {
            display: flex;
            align-items: center;
            gap: 12px;
            background: rgba(15, 23, 42, 0.4);
            border-radius: 12px;
            padding: 10px 14px;
        }
        .manual-icon {
            font-size: 1.3rem;
            background: rgba(255, 255, 255, 0.05);
            width: 38px;
            height: 38px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .manual-text {
            display: flex;
            flex-direction: column;
        }
        .manual-text .cmd { font-size: 0.85rem; font-weight: 700; color: #fff; }
        .manual-text .desc { font-size: 0.75rem; color: var(--muted); }

        .toast {
            margin-top: 14px;
            font-size: 0.85rem;
            color: #34d399;
            text-align: center;
            padding: 10px;
            border-radius: 10px;
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.3);
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="logo-tag">ESP32 Pomodoro</span>
            <h1>Configurar Duraciones</h1>
            <p class="subtitle">Personaliza tus intervalos de tiempo y descansos</p>
        </div>

        <!-- FASE FOCUS -->
        <div class="section-title focus">🔴 Sesión Focus</div>
        <div class="time-inputs">
            <div class="input-box">
                <label>Minutos</label>
                <input type="number" id="focus-m" min="0" max="180" value="0">
            </div>
            <div class="input-box">
                <label>Segundos</label>
                <input type="number" id="focus-s" min="0" max="59" value="5">
            </div>
        </div>

        <!-- FASE DESCANSO CORTO -->
        <div class="section-title short">🔵 Descanso Corto</div>
        <div class="time-inputs">
            <div class="input-box">
                <label>Minutos</label>
                <input type="number" id="short-m" min="0" max="60" value="0">
            </div>
            <div class="input-box">
                <label>Segundos</label>
                <input type="number" id="short-s" min="0" max="59" value="3">
            </div>
        </div>

        <!-- OPCIONES DESCANSO LARGO -->
        <div class="card-option">
            <div class="toggle-row">
                <span class="toggle-label">Activar Descanso Largo</span>
                <label class="switch">
                    <input type="checkbox" id="long-active" checked>
                    <span class="slider"></span>
                </label>
            </div>
            
            <div class="section-title long" style="margin-top: 12px;">🟢 Descanso Largo</div>
            <div class="time-inputs" style="margin-bottom: 12px;">
                <div class="input-box">
                    <label>Minutos</label>
                    <input type="number" id="long-m" min="0" max="60" value="0">
                </div>
                <div class="input-box">
                    <label>Segundos</label>
                    <input type="number" id="long-s" min="0" max="59" value="6">
                </div>
            </div>

            <div class="input-box">
                <label>Ciclos Focus Requeridos (Mínimo 2)</label>
                <input type="number" id="long-cycles" min="2" max="20" value="4">
            </div>
        </div>

        <button class="btn-save" onclick="guardarConfig()">Guardar Configuración</button>
        <div id="toast" class="toast">¡Configuración guardada correctamente!</div>

        <!-- GUÍA RÁPIDA DEL BOTÓN DE GESTOS -->
        <div class="manual-card">
            <div class="manual-title">🕹️ Guía de Gestos (Botón 2 - GPIO 22)</div>
            <div class="manual-grid">
                <div class="manual-item">
                    <div class="manual-icon">⏸️</div>
                    <div class="manual-text">
                        <span class="cmd">1 Clic</span>
                        <span class="desc">Pausar / Reanudar (Luz parpadea sin sonido)</span>
                    </div>
                </div>
                <div class="manual-item">
                    <div class="manual-icon">🔄</div>
                    <div class="manual-text">
                        <span class="cmd">2 Clics</span>
                        <span class="desc">Reiniciar tiempo de la fase actual a 0s (Tono doble)</span>
                    </div>
                </div>
                <div class="manual-item">
                    <div class="manual-icon">🏠</div>
                    <div class="manual-text">
                        <span class="cmd">Mantener 2s</span>
                        <span class="desc">Volver a Standby / Espera (Tono descendente)</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function cargarConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                
                if (data.tiempo_focus !== undefined) {
                    document.getElementById('focus-m').value = Math.floor(data.tiempo_focus / 60);
                    document.getElementById('focus-s').value = data.tiempo_focus % 60;
                }
                if (data.tiempo_descanso_corto !== undefined) {
                    document.getElementById('short-m').value = Math.floor(data.tiempo_descanso_corto / 60);
                    document.getElementById('short-s').value = data.tiempo_descanso_corto % 60;
                }
                if (data.tiempo_descanso_largo !== undefined) {
                    document.getElementById('long-m').value = Math.floor(data.tiempo_descanso_largo / 60);
                    document.getElementById('long-s').value = data.tiempo_descanso_largo % 60;
                }
                if (data.descanso_largo_activo !== undefined) {
                    document.getElementById('long-active').checked = data.descanso_largo_activo;
                }
                if (data.ciclos_para_descanso_largo !== undefined) {
                    document.getElementById('long-cycles').value = data.ciclos_para_descanso_largo;
                }
            } catch(e) {}
        }

        async function guardarConfig() {
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
            const longCycles = Math.max(2, parseInt(document.getElementById('long-cycles').value) || 4);

            if (totalFocus <= 0 || totalShort <= 0 || (longActive && totalLong <= 0)) {
                alert('Las duraciones de los intervalos deben ser mayores a 0 segundos.');
                return;
            }

            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tiempo_focus: totalFocus,
                        tiempo_descanso_corto: totalShort,
                        tiempo_descanso_largo: totalLong,
                        descanso_largo_activo: longActive,
                        ciclos_para_descanso_largo: longCycles
                    })
                });
                const toast = document.getElementById('toast');
                toast.style.display = 'block';
                setTimeout(() => toast.style.display = 'none', 3000);
            } catch(e) {
                alert('Error al comunicar con la ESP32.');
            }
        }

        cargarConfig();
    </script>
</body>
</html>
"""
