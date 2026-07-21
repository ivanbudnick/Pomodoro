import time
import socket
import network
import config
import pomodoro
import html_template

try:
    import ujson as json
except ImportError:
    import json

server_socket = None

# --- CONEXIÓN WIFI ---
def connect_wifi():
    """Establece conexión a la red WiFi configurada de forma segura contra Soft Reboots"""
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print("\n==========================================")
            print(" ¡CONECTADO A WIFI EXITOSAMENTE!")
            print(" Dirección IP de la ESP32: http://{}".format(ip))
            print("==========================================\n")
            return ip

        try:
            wlan.active(False)
            time.sleep_ms(100)
        except:
            pass
            
        wlan.active(True)

        if config.WIFI_SSID == "TU_RED_WIFI" or not config.WIFI_SSID:
            print("\n[INFO] WiFi no configurado (SSID por defecto). Iniciando en modo offline.")
            return "Offline"

        print("Conectando a WiFi '{}'...".format(config.WIFI_SSID))
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        timeout = 15
        start = time.time()
        while not wlan.isconnected() and (time.time() - start) < timeout:
            time.sleep(0.5)
            print(".", end="")
        print("")
        
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print("\n==========================================")
            print(" ¡CONECTADO A WIFI EXITOSAMENTE!")
            print(" Dirección IP de la ESP32: http://{}".format(ip))
            print("==========================================\n")
            return ip
        else:
            print("\n[ADVERTENCIA] No se pudo conectar a la red WiFi. Iniciando en modo offline.")
            return "Offline"
    except Exception as e:
        print("\n[ADVERTENCIA] Error en módulo WiFi ({}). Iniciando en modo offline.".format(e))
        return "Offline"

def sincronizar_config_pc():
    """Descarga e impone la última configuración guardada en la base de datos de la PC"""
    try:
        import urequests
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

def enviar_config_a_pc():
    """Respalda la configuración actual de la ESP32 en la base de datos de la PC"""
    try:
        import urequests
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

# --- PROCESAMIENTO DE PARÁMETROS Y CLIENTES HTTP ---
def procesar_config_query(query_str):
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


def atender_cliente_http(conn):
    try:
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
        
        # Ruta Principal Dashboard /
        if ruta == '/' or ruta.startswith('/?'):
            if '?' in ruta:
                procesar_config_query(ruta.split('?', 1)[1])
            header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n"
            conn.sendall(header)
            
            # Enviar la página en fragmentos para evitar problemas de buffer y memoria en MicroPython
            html_data = html_template.HTML_PAGE
            chunk_size = 512
            for i in range(0, len(html_data), chunk_size):
                conn.sendall(html_data[i:i+chunk_size])
            
        # API /api/config (GET y POST)
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

        # API /api/state (GET)
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
    """Inicializa el socket del servidor HTTP en el puerto 80"""
    global server_socket
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', 80))
        server_socket.listen(5)
        server_socket.setblocking(False)
        print("Servidor HTTP iniciado en puerto 80. Bucle Pomodoro activo.")
    except Exception as e:
        print("[ADVERTENCIA] No se pudo iniciar el servidor HTTP ({}). El Pomodoro funcionará en modo local.".format(e))

def atender_peticiones_http():
    """Verifica si hay peticiones HTTP entrantes de forma no bloqueante"""
    if server_socket is not None:
        try:
            conn, addr = server_socket.accept()
            atender_cliente_http(conn)
        except OSError:
            pass
