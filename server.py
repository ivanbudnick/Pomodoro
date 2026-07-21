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

        # Reiniciar interfaz WiFi para evitar 'Wifi Internal State Error' en Soft Reboots
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

# --- PROCESAMIENTO DE PARÁMETROS Y CLIENTES HTTP ---
def procesar_config_query(query_str):
    for par in query_str.split('&'):
        if '=' in par:
            k, v = par.split('=', 1)
            try:
                val = int(v)
                if val > 0:
                    if k in ('rojo', 'tiempo_rojo'):
                        config.tiempo_rojo_s = val
                        print("[HTTP] Tiempo LED Rojo actualizado a: {}s".format(config.tiempo_rojo_s))
                    elif k in ('azul', 'tiempo_azul'):
                        config.tiempo_azul_s = val
                        print("[HTTP] Tiempo LED Azul actualizado a: {}s".format(config.tiempo_azul_s))
            except ValueError:
                pass

def procesar_config_body(body_str):
    try:
        data = json.loads(body_str)
        if 'tiempo_rojo' in data and int(data['tiempo_rojo']) > 0:
            config.tiempo_rojo_s = int(data['tiempo_rojo'])
            print("[HTTP POST] Tiempo LED Rojo actualizado a: {}s".format(config.tiempo_rojo_s))
        elif 'rojo' in data and int(data['rojo']) > 0:
            config.tiempo_rojo_s = int(data['rojo'])
            
        if 'tiempo_azul' in data and int(data['tiempo_azul']) > 0:
            config.tiempo_azul_s = int(data['tiempo_azul'])
            print("[HTTP POST] Tiempo LED Azul actualizado a: {}s".format(config.tiempo_azul_s))
        elif 'azul' in data and int(data['azul']) > 0:
            config.tiempo_azul_s = int(data['azul'])
    except Exception as e:
        print("[HTTP POST ERROR] Error decodificando JSON:", e)

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
            conn.sendall(header + html_template.HTML_PAGE)
            
        # API /api/config (GET y POST)
        elif ruta == '/api/config':
            if metodo == 'POST':
                if '\r\n\r\n' in req_text:
                    body = req_text.split('\r\n\r\n', 1)[1]
                    procesar_config_body(body)
                body_res = json.dumps({"status": "success", "tiempo_rojo": config.tiempo_rojo_s, "tiempo_azul": config.tiempo_azul_s})
            else:
                body_res = json.dumps({"tiempo_rojo": config.tiempo_rojo_s, "tiempo_azul": config.tiempo_azul_s})
                
            header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n"
            conn.sendall(header + body_res)
            
        elif ruta.startswith('/api/config?'):
            procesar_config_query(ruta.split('?', 1)[1])
            body_res = json.dumps({"status": "success", "tiempo_rojo": config.tiempo_rojo_s, "tiempo_azul": config.tiempo_azul_s})
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
