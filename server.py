# ==============================================================================
# SERVIDOR HTTP EMBUDIDO Y CONFIGURADOR DE RED (PORTAL CAUTIVO)
# ==============================================================================
# Este módulo provee toda la infraestructura de red del Pomodoro Pro:
# 1. Portal Cautivo (WiFi Manager): Si no hay WiFi configurado o la conexión falla,
#    el ESP32 se convierte en un Punto de Acceso (AP) y levanta un servidor HTTP
#    en 192.168.4.1 para que el usuario ingrese la SSID y la contraseña.
# 2. Servidor Web Dashboard: Sirve la interfaz web unificada (html_template.py)
#    y expone APIs REST en JSON para configurar parámetros o leer el estado en vivo.
# 3. Sincronización Remota: Al iniciar en línea, sincroniza los tiempos con la
#    base de datos de la PC (Flask) y viceversa.
#
# Gestión de Memoria (RAM):
# Para evitar errores fatales de falta de memoria (ENOMEM), las páginas HTML
# pesadas se sirven por trozos o "chunks" de 512 bytes. Esto previene que el buffer
# de red consuma bloques de memoria contiguos excesivamente grandes.

import time
import socket
import network
import config
import pomodoro

try:
    import ujson as json
except ImportError:
    import json

try:
    import urequests
except ImportError:
    urequests = None

# Instancia global del socket del servidor
server_socket = None

# ==============================================================================
# PORTAL CAUTIVO (WIFI MANAGER DE ARRANQUE)
# ==============================================================================

def run_captive_portal():
    """
    Inicia un punto de acceso (AP) local e inicia un servidor socket síncrono.
    Cualquier petición al puerto 80 del servidor servirá un formulario web
    con un escaneo en vivo de las redes Wi-Fi cercanas.
    """
    import network
    import socket
    import time
    
    # 1. Escanear redes cercanas utilizando la interfaz STA
    wlan_sta = network.WLAN(network.STA_IF)
    wlan_sta.active(True)
    print("[WIFI AP] Escaneando redes Wi-Fi cercanas...")
    try:
        networks = wlan_sta.scan()
    except Exception as e:
        print("[WIFI AP ERROR] No se pudo escanear redes:", e)
        networks = []
        
    # Desactivar STA temporalmente para liberar la radio y evitar interferencia
    try:
        wlan_sta.active(False)
    except:
        pass
        
    # Filtrar duplicados en redes encontradas (misma SSID en distintos canales)
    seen = set()
    unique_ssids = []
    for net in networks:
        try:
            ssid = net[0].decode('utf-8', 'ignore').strip()
            if ssid and ssid not in seen:
                seen.add(ssid)
                unique_ssids.append(ssid)
        except:
            pass
            
    # Construir opciones del selector <select> en HTML
    options = ""
    for ssid in unique_ssids:
        options += '<option value="{0}">{0}</option>\n'.format(ssid)
    if not options:
        options = '<option value="">No se encontraron redes</option>'

    # 2. Configurar y activar el Access Point local (AP)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    # Dirección IP predeterminada: 192.168.4.1
    ap.ifconfig(('192.168.4.1', '255.255.255.0', '192.168.4.1', '8.8.8.8'))
    ap.config(essid="Pomodoro-WiFi-Manager", authmode=network.AUTH_OPEN)
    
    ap_ip = ap.ifconfig()[0]
    print("\n==========================================")
    print(" ¡PORTAL CAUTIVO DE CONFIGURACIÓN ACTIVO!")
    print(" Conéctese a la red Wi-Fi: Pomodoro-WiFi-Manager")
    print(" Abra un navegador e ingrese a: http://{}".format(ap_ip))
    print("==========================================\n")
    
    # 3. Abrir socket TCP de escucha síncrono en puerto 80
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(1)
    
    html_template_page = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuración Wi-Fi Pomodoro</title>
    <style>
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: #06080f;
            background-image: radial-gradient(circle at top, #141725, #06080f);
            color: #f3f4f6;
            margin: 0;
            padding: 24px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            box-sizing: border-box;
        }
        .card {
            width: 100%;
            max-width: 400px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 18px;
            padding: 32px;
            box-sizing: border-box;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        h2 {
            margin-top: 0;
            margin-bottom: 24px;
            font-size: 1.5rem;
            font-weight: 700;
            color: #fff;
            text-align: center;
        }
        .field-label {
            display: block;
            font-size: 0.8rem;
            color: #8a8f98;
            margin-bottom: 6px;
            text-align: left;
        }
        select, input {
            width: 100%;
            padding: 12px 16px;
            margin-bottom: 20px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.01);
            color: #fff;
            border-radius: 10px;
            font-size: 0.95rem;
            box-sizing: border-box;
            outline: none;
            transition: border-color 0.2s;
        }
        select:focus, input:focus {
            border-color: rgba(255, 255, 255, 0.2);
        }
        select option {
            background: #0d0f18;
            color: #fff;
        }
        button {
            width: 100%;
            padding: 14px;
            background: #5b8ce0;
            border: none;
            color: #fff;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #4a7bd0;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>Configurar Wi-Fi</h2>
        <form method="POST" action="/save">
            <label class="field-label">Seleccionar Red Cercana</label>
            <select name="ssid">
                [OPTIONS]
            </select>
            <label class="field-label">Contraseña de la Red</label>
            <input type="password" name="password" placeholder="Contraseña">
            <button type="submit">Conectar y Reiniciar</button>
        </form>
    </div>
</body>
</html>"""

    html_success = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuración Guardada</title>
    <style>
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: #06080f;
            color: #52be90;
            text-align: center;
            padding: 40px 24px;
        }
        h2 { color: #52be90; font-size: 1.8rem; margin-bottom: 12px; }
        p { color: #8a8f98; font-size: 1rem; }
    </style>
</head>
<body>
    <h2>¡Configuración Guardada!</h2>
    <p>La ESP32 se está reiniciando para conectarse a la red <strong>[SSID]</strong>.</p>
</body>
</html>"""

    while True:
        try:
            conn, addr = s.accept()
            print("[WIFI AP] Conexión entrante desde:", addr)
            conn.settimeout(1.0)
            req_data = conn.recv(1024)
            if not req_data:
                print("[WIFI AP] Petición vacía recibida. Cerrando conexión.")
                conn.close()
                continue
                
            req = req_data.decode('utf-8', 'ignore')
            print("[WIFI AP] Petición HTTP recibida (línea 1):", req.split('\r\n')[0])
            
            # Procesar el envío del formulario (POST)
            if "POST /save" in req:
                body = ""
                if '\r\n\r\n' in req:
                    body = req.split('\r\n\r\n', 1)[1]
                
                # Leer bytes remanentes del body si no se completó en la primera ráfaga
                if not body or '=' not in body:
                    try:
                        time.sleep_ms(50)
                        more = conn.recv(512).decode('utf-8', 'ignore')
                        body += more
                    except:
                        pass
                
                # Decodificar de forma artesanal parámetros multipart (SSID y Contraseña)
                params = {}
                for part in body.split('&'):
                    if '=' in part:
                        k, v = part.split('=', 1)
                        v = v.replace('+', ' ')
                        res = ""
                        i = 0
                        while i < len(v):
                            if v[i] == '%':
                                try:
                                    res += chr(int(v[i+1:i+3], 16))
                                    i += 3
                                except:
                                    res += v[i]
                                    i += 1
                            else:
                                res += v[i]
                                i += 1
                        params[k] = res
                        
                ssid = params.get("ssid", "")
                password = params.get("password", "")
                
                print("[WIFI AP] SSID a conectar recibida:", ssid)
                
                # Guardar de forma persistente las nuevas credenciales en wifi.json
                with open("wifi.json", "w") as f:
                    json.dump({"ssid": ssid, "password": password}, f)
                
                # Responder con éxito y forzar un reinicio del microcontrolador
                resp_success = html_success.replace("[SSID]", ssid)
                header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n"
                conn.sendall(header)
                conn.sendall(resp_success)
                conn.close()
                print("[WIFI AP] Respuesta enviada. Reiniciando la placa...")
                
                time.sleep(2)
                import machine
                machine.reset()
            else:
                # Servir el formulario de configuración en fragmentos pequeños (Streaming)
                resp_form = html_template_page.replace("[OPTIONS]", options)
                header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n"
                conn.sendall(header)
                
                chunk_size = 512
                for i in range(0, len(resp_form), chunk_size):
                    conn.sendall(resp_form[i:i+chunk_size])
                conn.close()
                print("[WIFI AP] Formulario de configuración servido y conexión cerrada.")
        except Exception as e:
            print("[WIFI AP ERROR]", e)
            try:
                conn.close()
            except:
                pass

# ==============================================================================
# CONEXIÓN Y SINCRONIZACIÓN DE RED
# ==============================================================================

def _retornar_ip_conexion(wlan):
    """
    Helper para imprimir información de red en la consola y retornar la IP.
    Evita código duplicado al evaluar el estado de conexión de la placa.
    """
    ip = wlan.ifconfig()[0]
    print("\n==========================================")
    print(" ¡CONECTADO A WIFI EXITOSAMENTE!")
    print(" Dirección IP de la ESP32: http://{}".format(ip))
    print("==========================================\n")
    return ip

def connect_wifi():
    """
    Conecta al Punto de Acceso configurado localmente.
    Si no hay credenciales o la conexión falla tras 12 segundos,
    inicia automáticamente el Portal Cautivo de configuración.
    """
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            return _retornar_ip_conexion(wlan)

        try:
            wlan.active(False)
            time.sleep_ms(100)
        except:
            pass
            
        wlan.active(True)

        if not config.WIFI_SSID:
            print("\n[WIFI] No se detectaron credenciales Wi-Fi guardadas.")
            run_captive_portal()
            return "Offline"

        print("Conectando a WiFi '{}'...".format(config.WIFI_SSID))
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        
        # Espera activa no bloqueante de 12 segundos por timeout
        timeout = 12
        start = time.time()
        while not wlan.isconnected() and (time.time() - start) < timeout:
            time.sleep(0.5)
            print(".", end="")
        print("")
        
        if wlan.isconnected():
            return _retornar_ip_conexion(wlan)
        else:
            print("\n[ADVERTENCIA] No se pudo conectar a la red WiFi '{}'.".format(config.WIFI_SSID))
            run_captive_portal()
            return "Offline"
    except Exception as e:
        print("\n[ADVERTENCIA] Error en módulo WiFi ({}).".format(e))
        run_captive_portal()
        return "Offline"

def sincronizar_config_pc():
    """Descarga e impone la configuración horaria de la Base de Datos centralizada (Flask) en la PC"""
    if urequests is None:
        print("[SYNC WARNING] Modulo urequests no disponible.")
        return
    try:
        url = config.FLASK_SERVER_URL.replace("/datos", "/api/latest_config")
        print("[SYNC] Descargando última configuración de la PC desde {}...".format(url))
        res = urequests.get(url)
        if res.status_code == 200:
            data = res.json()
            if data:
                config.tiempo_focus_s = int(data.get("tiempo_focus", config.tiempo_focus_s))
                config.tiempo_descanso_corto_s = int(data.get("tiempo_descanso_corto", config.tiempo_descanso_corto_s))
                config.tiempo_descanso_largo_s = int(data.get("tiempo_descanso_largo", config.tiempo_descanso_largo_s))
                config.descanso_largo_activo = bool(data.get("descanso_largo_activo", config.descanso_largo_activo))
                config.ciclos_para_descanso_largo = int(data.get("ciclos_para_descanso_largo", config.ciclos_para_descanso_largo))
                config.guardar_a_disco()
                print("[SYNC SUCCESS] Configuración sincronizada con la base de datos de la PC.")
            else:
                print("[SYNC INFO] No hay configuraciones en la BD de la PC aún.")
        res.close()
    except Exception as e:
        print("[SYNC WARNING] No se pudo conectar a la PC para sincronizar:", e)
    finally:
        import gc
        gc.collect()

def enviar_config_a_pc():
    """Respalda la configuración actual del ESP32 en la base de datos centralizada de la PC"""
    if urequests is None:
        print("[SYNC REPORT WARNING] Modulo urequests no disponible.")
        return
    try:
        url = config.FLASK_SERVER_URL.replace("/datos", "/api/save_config")
        payload = {
            "tiempo_focus": config.tiempo_focus_s,
            "tiempo_descanso_corto": config.tiempo_descanso_corto_s,
            "tiempo_descanso_largo": config.tiempo_descanso_largo_s,
            "descanso_largo_activo": config.descanso_largo_activo,
            "ciclos_para_descanso_largo": config.ciclos_para_descanso_largo
        }
        res = urequests.post(url, json=payload)
        print("[SYNC REPORT] Configuración respaldada en PC (DB). HTTP Status:", res.status_code)
        res.close()
    except Exception as e:
        print("[SYNC REPORT WARNING] No se pudo respaldar la configuración en la PC:", e)
    finally:
        import gc
        gc.collect()

# ==============================================================================
# PROCESADORES DE APIS HTTP
# ==============================================================================

def procesar_config_query(query_str):
    """Parsea argumentos pasados en la URL (GET query parameters) como /?focus=1500"""
    updated = False
    for par in query_str.split('&'):
        if '=' in par:
            k, v = par.split('=', 1)
            try:
                val = int(v)
                if val > 0:
                    if k in ('focus', 'tiempo_focus', 'rojo', 'tiempo_rojo'):
                        config.tiempo_focus_s = val
                        updated = True
                    elif k in ('descanso_corto', 'tiempo_descanso_corto', 'azul', 'tiempo_azul'):
                        config.tiempo_descanso_corto_s = val
                        updated = True
                    elif k in ('descanso_largo', 'tiempo_descanso_largo', 'verde', 'tiempo_verde'):
                        config.tiempo_descanso_largo_s = val
                        updated = True
                    elif k == 'ciclos_descanso_largo':
                        config.ciclos_para_descanso_largo = max(2, val)
                        updated = True
            except ValueError:
                pass
    if updated:
        config.guardar_a_disco()
        enviar_config_a_pc()

def procesar_config_body(body_str):
    """Parsea el cuerpo JSON de peticiones POST para sobreescribir la configuración"""
    try:
        data = json.loads(body_str)
        updated = False
        if 'tiempo_focus' in data and int(data['tiempo_focus']) > 0:
            config.tiempo_focus_s = int(data['tiempo_focus'])
            updated = True
        elif 'tiempo_rojo' in data and int(data['tiempo_rojo']) > 0:
            config.tiempo_focus_s = int(data['tiempo_rojo'])
            updated = True

        if 'tiempo_descanso_corto' in data and int(data['tiempo_descanso_corto']) > 0:
            config.tiempo_descanso_corto_s = int(data['tiempo_descanso_corto'])
            updated = True
        elif 'tiempo_azul' in data and int(data['tiempo_azul']) > 0:
            config.tiempo_descanso_corto_s = int(data['tiempo_azul'])
            updated = True

        if 'tiempo_descanso_largo' in data and int(data['tiempo_descanso_largo']) > 0:
            config.tiempo_descanso_largo_s = int(data['tiempo_descanso_largo'])
            updated = True

        if 'descanso_largo_activo' in data:
            config.descanso_largo_activo = bool(data['descanso_largo_activo'])
            updated = True

        if 'ciclos_para_descanso_largo' in data and int(data['ciclos_para_descanso_largo']) >= 2:
            config.ciclos_para_descanso_largo = int(data['ciclos_para_descanso_largo'])
            updated = True
            
        if updated:
            print("[HTTP CONFIG] Configuración de duraciones actualizada exitosamente.")
            config.guardar_a_disco()
            enviar_config_a_pc()
    except Exception as e:
        print("[HTTP POST ERROR] Error decodificando JSON de configuración:", e)

# ==============================================================================
# ATENCIÓN DE CLIENTES Y SERVIDOR
# ==============================================================================

def atender_cliente_http(conn):
    """
    Parsea las rutas HTTP del cliente y responde con cabeceras y payloads.
    - GET /: Sirve el Dashboard HTML de forma fragmentada.
    - GET /api/config: Retorna la configuración horaria en JSON.
    - POST /api/config: Recibe y guarda la nueva configuración JSON.
    - GET /api/state: Retorna el estado en tiempo real del reloj.
    """
    try:
        pomodoro.registrar_actividad() # Reactivar timer de Deep Sleep ante interacción web
        conn.settimeout(0.3)
        raw_data = conn.recv(1024)
        if not raw_data:
            conn.close()
            return
            
        req_text = raw_data.decode('utf-8', 'ignore')
        lineas = req_text.split('\r\n')
        if not lineas or not lineas[0]:
            conn.close()
            return
            
        partes = lineas[0].split(' ')
        if len(partes) < 2:
            conn.close()
            return
            
        metodo = partes[0]
        ruta = partes[1]
        
        # Ruta raíz: Dashboard
        if ruta == '/' or ruta.startswith('/?'):
            if '?' in ruta:
                procesar_config_query(ruta.split('?', 1)[1])
            header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n"
            conn.sendall(header)
            
            # Streaming por fragmentos de 512 bytes leyendo directamente de Flash para prevenir ENOMEM
            try:
                with open("dashboard.html", "r") as f:
                    while True:
                        chunk = f.read(512)
                        if not chunk:
                            break
                        conn.sendall(chunk)
            except Exception as e:
                print("[HTTP SERVER ERROR] No se pudo leer dashboard.html:", e)
            
        # API Configuración
        elif ruta == '/api/config':
            if metodo == 'POST':
                if '\r\n\r\n' in req_text:
                    body = req_text.split('\r\n\r\n', 1)[1]
                    procesar_config_body(body)
                body_res = json.dumps({
                    "status": "success",
                    "tiempo_focus": config.tiempo_focus_s,
                    "tiempo_descanso_corto": config.tiempo_descanso_corto_s,
                    "tiempo_descanso_largo": config.tiempo_descanso_largo_s,
                    "descanso_largo_activo": config.descanso_largo_activo,
                    "ciclos_para_descanso_largo": config.ciclos_para_descanso_largo
                })
            else:
                body_res = json.dumps({
                    "tiempo_focus": config.tiempo_focus_s,
                    "tiempo_descanso_corto": config.tiempo_descanso_corto_s,
                    "tiempo_descanso_largo": config.tiempo_descanso_largo_s,
                    "descanso_largo_activo": config.descanso_largo_activo,
                    "ciclos_para_descanso_largo": config.ciclos_para_descanso_largo
                })
                
            header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n"
            conn.sendall(header + body_res)

        # API Estado en Tiempo Real
        elif ruta == '/api/state':
            body_res = json.dumps(pomodoro.obtener_dict_estado())
            header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n"
            conn.sendall(header + body_res)
            
        else:
            header = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
            conn.sendall(header + "404 No Encontrado")
            
    except Exception as e:
        pass
    finally:
        try:
            conn.close()
        except:
            pass

def iniciar_servidor_http():
    """Abre el socket principal de escucha TCP puerto 80 de forma no bloqueante"""
    global server_socket
    import gc
    gc.collect()
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', 80))
        server_socket.listen(5)
        # Configurar en modo no bloqueante para evitar detener la máquina de estados en main.py
        server_socket.setblocking(False)
        print("Servidor HTTP iniciado en puerto 80. Bucle Pomodoro activo.")
    except Exception as e:
        print("[ADVERTENCIA] No se pudo iniciar el servidor HTTP ({}). El Pomodoro funcionará en modo local.".format(e))

def atender_peticiones_http():
    """Llamado periódicamente para verificar de forma instantánea si hay peticiones TCP pendientes"""
    if server_socket is not None:
        try:
            conn, addr = server_socket.accept()
            atender_cliente_http(conn)
        except OSError:
            # Captura el error de 'no data available' producido al ser no bloqueante
            pass
