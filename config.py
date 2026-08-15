# ==============================================================================
# CONFIGURACIÓN GENERAL DEL POMODORO PRO
# ==============================================================================
# Este archivo centraliza todas las constantes del hardware, parámetros del
# temporizador Pomodoro, y rutinas de persistencia local en la Flash del ESP32.
#
# Al ser MicroPython, las variables globales aquí definidas pueden ser modificadas
# en tiempo de ejecución (por ejemplo, desde el servidor web) y guardadas
# de forma persistente.

# --- CONFIGURACIÓN DE WIFI Y SERVIDOR EN LA NUBE ---
WIFI_SSID = ""            # Nombre de la red WiFi (se carga de wifi.json)
WIFI_PASSWORD = ""        # Contraseña de la red WiFi (se carga de wifi.json)
DEFAULT_SERVER_URL = "https://3d-moai.vercel.app" 
SERVER_URL = DEFAULT_SERVER_URL
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC_SESIONES = "pomodoro/sesiones"
last_sync_time = 0

try:
    from version import VERSION
except ImportError:
    VERSION = "1.0.1"

# Identificación Única de Hardware (MAC address de la ESP32)
import machine
import ubinascii
try:
    DEVICE_ID = ubinascii.hexlify(machine.unique_id()).decode('utf-8')
except Exception:
    DEVICE_ID = "esp32_unknown"

# --- CONFIGURACIÓN DE ACTUALIZACIONES OTA (GITHUB) ---
OTA_GITHUB_USER = "ivanbudnick"   # Usuario de GitHub propietario del repositorio
OTA_GITHUB_REPO = "Pomodoro"       # Nombre del repositorio
OTA_GITHUB_BRANCH = "main"         # Rama a la que consultar (main/master)


# --- CONFIGURACIÓN DE PINES (ESP32) ---
# Se utiliza el GPIO 25 para el botón único para evitar los ruidos
# analógicos causados por el oscilador del cristal de 32kHz (presente en GPIO 32/33 en ESP-32S).
PIN_BTN = 25                   # Botón Único de Control y Gestos (PULL-UP interno, capaz de RTC)
PIN_LED_ROJO = 14              # Pin PWM LED Canal Rojo (Curva Enfoque)
PIN_LED_VERDE = 27             # Pin PWM LED Canal Verde (Descanso Largo)
PIN_LED_AZUL = 26              # Pin PWM LED Canal Azul (Descanso Corto / Alerta)
PIN_LED_INTERNO = 2            # Pin del LED incorporado (Built-in) del ESP32
PIN_BUZZER = 13                # Pin PWM para el zumbador piezoeléctrico activo/pasivo

# --- CONFIGURACIÓN DE FOTORESISTENCIA (LDR) ---
# Permite regular automáticamente el brillo del LED RGB según la luz ambiental.
PIN_LDR = 34                   # Pin de entrada ADC (canal ADC1_CH6 en ESP32)
LDR_MIN_VAL = 10               # Umbral ADC inferior (oscuridad total o sensor tapado)
LDR_MAX_VAL = 150              # Umbral ADC superior (iluminación ambiente de oficina)
LDR_MIN_FACTOR = 0.05          # Brillo mínimo (5% de intensidad) para que el LED no se apague del todo en la oscuridad
LDR_MAX_FACTOR = 1.0           # Brillo máximo (100% de intensidad) en entornos iluminados

# --- CONFIGURACIÓN DE PWM ---
PWM_FREQ_LED = 1000            # Frecuencia en Hz para la modulación RGB (evita parpadeo visible)
DUTY_MAX = 1023                # Valor ciclo de trabajo máximo (resolución de 10 bits en ESP32)
DUTY_PISO = int(DUTY_MAX / 100)  # Brillo base mínimo (~1%) para la curva exponencial progresiva
BUZZER_DUTY = 512              # Volumen medio del buzzer (onda cuadrada al 50% de ciclo de trabajo)

# --- CONSTANTES DE TIEMPO (ms) ---
INTERVALO_TITILO_STANDBY_MS = 500  # Velocidad de parpadeo del color Amarillo en Standby
INTERVALO_ALERTA_MS = 500          # Velocidad de parpadeo y pitido en Alerta
TIEMPO_TRANSICION_PITIDO_MS = 100  # Duración de pitidos rápidos de transición
DEBOUNCE_BOTON_MS = 300            # Tiempo mínimo de espera para filtrar falsas pulsaciones por rebote físico
LOOP_SLEEP_MS = 10                 # Tiempo de espera en cada iteración del bucle principal
TIEMPO_INACTIVIDAD_SLEEP_MS = 60000  # Tiempo (60s) sin interacción para activar el Deep Sleep y ahorrar batería

# --- CONSTANTES DE GESTOS PARA BOTÓN 2 ---
TIEMPO_MANTENER_STANDBY_MS = 2000  # Duración (2s) de presión continua para forzar regreso a Standby
VENTANA_DOBLE_CLIC_MS = 400        # Ventana máxima de tiempo (400ms) entre dos pulsaciones para detectar doble clic

# --- FRECUENCIAS DEL BUZZER (Hz - Notas Armónicas y Suaves) ---
FREQ_BUZZER_INICIO = 523        # Nota Do5 (C5) - Tono motivador de inicio de sesión
FREQ_BUZZER_CAMBIO_ESTADO = 659  # Nota Mi5 (E5) - Fin de la sesión de enfoque
FREQ_BUZZER_TRANSICION = 784    # Nota Sol5 (G5) - Fin de descansos
FREQ_BUZZER_ALERTA = 523         # Nota Do5 (C5) - Tono sutil de advertencia
FREQ_BUZZER_RESET_FASE = 784     # Nota Sol5 (G5) - Tono de confirmación de reseteo de fase
FREQ_BUZZER_IDLE = 440           # Nota La4 (A4) - Tono de apagado o retorno a Standby

# --- PARÁMETROS DE POMODORO Y DESCANSO LARGO CONFIGURABLES ---
# Estos valores representan los segundos predeterminados de cada fase y se pueden
# sobrescribir desde el panel web o base de datos.
tiempo_focus_s = 5           # Duración de sesión Focus (por defecto 5s para pruebas rápidas)
tiempo_descanso_corto_s = 3   # Duración de Descanso Corto (por defecto 3s para pruebas rápidas)
tiempo_descanso_largo_s = 6   # Duración de Descanso Largo (por defecto 6s para pruebas rápidas)

descanso_largo_activo = True  # Habilita / deshabilita el ciclo de descanso largo
ciclos_para_descanso_largo = 4 # Cantidad de sesiones de enfoque previas al descanso largo
# --- PERSISTENCIA LOCAL (JSON) EN FLASH DE LA ESP32 ---
def guardar_a_disco():
    """
    Serializa y guarda la configuración de tiempos en config.json.
    Esto permite que los cambios de tiempos persistan a reinicios o cortes de energía.
    """
    try:
        import ujson as json
        with open("config.json", "w") as f:
            json.dump({
                "tiempo_focus": tiempo_focus_s,
                "tiempo_descanso_corto": tiempo_descanso_corto_s,
                "tiempo_descanso_largo": tiempo_descanso_largo_s,
                "descanso_largo_activo": descanso_largo_activo,
                "ciclos_para_descanso_largo": ciclos_para_descanso_largo,
                "server_url": SERVER_URL,
                "ota_github_user": OTA_GITHUB_USER,
                "ota_github_repo": OTA_GITHUB_REPO,
                "ota_github_branch": OTA_GITHUB_BRANCH
            }, f)
        print("[CONFIG] Configuración guardada en config.json local.")
    except Exception as e:
        print("[CONFIG ERROR] No se pudo guardar config.json local:", e)

def cargar_de_disco():
    """
    Deserializa config.json para cargar la configuración guardada del usuario.
    """
    global tiempo_focus_s, tiempo_descanso_corto_s, tiempo_descanso_largo_s, descanso_largo_activo, ciclos_para_descanso_largo, SERVER_URL, OTA_GITHUB_USER, OTA_GITHUB_REPO, OTA_GITHUB_BRANCH
    try:
        import os
        import ujson as json
        try:
            os.stat("config.json")
        except OSError:
            print("[CONFIG INFO] No existe config.json local. Usando valores por defecto.")
            return
            
        debe_guardar = False
        with open("config.json", "r") as f:
            data = json.load(f)
            tiempo_focus_s = int(data.get("tiempo_focus", tiempo_focus_s))
            tiempo_descanso_corto_s = int(data.get("tiempo_descanso_corto", tiempo_descanso_corto_s))
            tiempo_descanso_largo_s = int(data.get("tiempo_descanso_largo", tiempo_descanso_largo_s))
            descanso_largo_activo = bool(data.get("descanso_largo_activo", descanso_largo_activo))
            ciclos_para_descanso_largo = int(data.get("ciclos_para_descanso_largo", ciclos_para_descanso_largo))
            
            saved_url = data.get("server_url", data.get("flask_server_url", SERVER_URL))
            # Quitar rutas "/datos" si venían de la versión anterior
            if saved_url.endswith("/datos"):
                saved_url = saved_url.replace("/datos", "")
                debe_guardar = True
                
            # Migración automática si el dominio guardado es el antiguo (pomodoro-mocha-one)
            if "pomodoro-mocha-one" in saved_url:
                print("[CONFIG] Detectado dominio antiguo. Migrando automáticamente a: {}".format(DEFAULT_SERVER_URL))
                saved_url = DEFAULT_SERVER_URL
                debe_guardar = True
                
            SERVER_URL = saved_url
            OTA_GITHUB_USER = data.get("ota_github_user", OTA_GITHUB_USER)
            OTA_GITHUB_REPO = data.get("ota_github_repo", OTA_GITHUB_REPO)
            OTA_GITHUB_BRANCH = data.get("ota_github_branch", OTA_GITHUB_BRANCH)
            
        if debe_guardar:
            guardar_a_disco()
            
        print("[CONFIG SUCCESS] Configuración cargada desde config.json local.")
        print_configuracion_actual()
    except Exception as e:
        print("[CONFIG ERROR] Fallo al leer config.json local:", e)

def print_configuracion_actual():
    """Muestra en la consola la configuración actual de tiempos en segundos"""
    print("[CONFIG] Tiempos activos: Focus={}s, Descanso Corto={}s, Descanso Largo={}s (Largo={}, Ciclos={})".format(
        tiempo_focus_s, tiempo_descanso_corto_s, tiempo_descanso_largo_s,
        "Activo" if descanso_largo_activo else "Inactivo", ciclos_para_descanso_largo
    ))
def cargar_wifi():
    """
    Carga el SSID y la contraseña WiFi guardados en wifi.json.
    Si no existen credenciales guardadas, la aplicación asume que
    se encuentra en primer inicio e inicia en modo Portal Cautivo.
    """
    global WIFI_SSID, WIFI_PASSWORD
    try:
        import os
        import ujson as json
        try:
            os.stat("wifi.json")
        except OSError:
            print("[WIFI CONFIG] No existe wifi.json local. Se iniciará en modo Portal Cautivo.")
            WIFI_SSID = ""
            WIFI_PASSWORD = ""
            return
            
        with open("wifi.json", "r") as f:
            data = json.load(f)
            WIFI_SSID = data.get("ssid", "")
            WIFI_PASSWORD = data.get("password", "")
        print("[WIFI CONFIG] Credenciales de Wi-Fi cargadas desde wifi.json.")
    except Exception as e:
        print("[WIFI CONFIG ERROR] Fallo al cargar wifi.json:", e)
        WIFI_SSID = ""
        WIFI_PASSWORD = ""

def _http_request_optimizado(method, url, payload=None):
    """
    Cliente HTTP de bajo nivel optimizado para MicroPython.
    - Utiliza HTTP/1.0 para evitar la decodificación de transferencias fragmentadas (chunked encoding).
    - Evita importar la librería urequests (ahorrando memoria de importación).
    - No parsea headers de respuesta para POST, liberando buffers SSL de inmediato.
    - Para GET, descarta headers línea por línea para evitar fragmentación del Heap.
    """
    import gc
    
    # Importaciones robustas con fallback para compatibilidad entre distintas versiones de MicroPython
    try:
        import socket
    except ImportError:
        import usocket as socket
        
    try:
        import ssl
    except ImportError:
        import ussl as ssl
        
    try:
        import json
    except ImportError:
        import ujson as json
    
    print("[HTTP DEBUG] Iniciando request: {} a {} (RAM libre pre-GC: {} bytes)".format(method, url, gc.mem_free()))
    gc.collect()
    gc.collect()
    print("[HTTP DEBUG] RAM libre post-GC: {} bytes".format(gc.mem_free()))
    
    # 1. Parsear URL de forma segura
    try:
        proto, _, host_path = url.split("/", 2)
        if "/" in host_path:
            host, path = host_path.split("/", 1)
            path = "/" + path
        else:
            host = host_path
            path = "/"
    except Exception as e:
        print("[HTTP ERROR] URL malformada:", url, e)
        return None
        
    use_ssl = proto.startswith("https")
    port = 443 if use_ssl else 80
    print("[HTTP DEBUG] URL Parsed: proto={}, host={}, path={}, port={}, use_ssl={}".format(proto, host, path, port, use_ssl))
    
    # 2. Resolver DNS
    try:
        print("[HTTP DEBUG] Resolviendo DNS para {}...".format(host))
        addr = socket.getaddrinfo(host, port)[0][-1]
        print("[HTTP DEBUG] DNS resuelto: {}".format(addr))
    except Exception as e:
        print("[HTTP ERROR] DNS fail:", e)
        return None
        
    s = None
    try:
        # 3. Crear y conectar Socket
        print("[HTTP DEBUG] Creando socket...")
        s = socket.socket()
        s.settimeout(5)
        
        # Evitar estado TIME_WAIT configurando SO_LINGER a 0
        try:
            import struct
            sol_socket = getattr(socket, "SOL_SOCKET", 1)
            so_linger = getattr(socket, "SO_LINGER", 13)
            s.setsockopt(sol_socket, so_linger, struct.pack('ii', 1, 0))
            print("[HTTP DEBUG] SO_LINGER establecido a 0 (evita TIME_WAIT).")
        except Exception as le:
            print("[HTTP DEBUG] No se pudo establecer SO_LINGER:", le)
            
        print("[HTTP DEBUG] Conectando a {}...".format(addr))
        s.connect(addr)
        print("[HTTP DEBUG] Socket conectado exitosamente.")
        
        # 4. Envolver en SSL si corresponde
        if use_ssl:
            print("[HTTP DEBUG] Envolviendo socket en SSL (RAM libre pre-wrap: {} bytes)...".format(gc.mem_free()))
            gc.collect()
            s = ssl.wrap_socket(s, server_hostname=host)
            try:
                s.settimeout(5)
            except Exception:
                pass
            
        # 5. Formatear y escribir la solicitud (HTTP/1.0)
        req = "{} {} HTTP/1.0\r\nHost: {}\r\n".format(method, path, host)
        
        body_bytes = None
        if payload is not None:
            body_bytes = json.dumps(payload).encode('utf-8')
            req += "Content-Type: application/json\r\nContent-Length: {}\r\n".format(len(body_bytes))
            
        req += "\r\n"
        
        full_req = req.encode('utf-8')
        if body_bytes:
            full_req += body_bytes
            
        print("[HTTP DEBUG] Escribiendo request (Cabeceras={} bytes, Body={} bytes, Total={} bytes)...".format(
            len(req.encode('utf-8')), len(body_bytes) if body_bytes else 0, len(full_req)))
        s.write(full_req)
        print("[HTTP DEBUG] Escribió request en socket.")
        
        # 6. Leer y evaluar primera línea de respuesta (Status)
        print("[HTTP DEBUG] Esperando línea de estado...")
        resp_line = s.readline()
        if not resp_line:
            print("[HTTP ERROR] Servidor cerró conexión sin respuesta.")
            return None
            
        status_line = resp_line.decode('utf-8')
        print("[HTTP DEBUG] Línea de estado recibida: '{}'".format(status_line.strip()))
        
        parts = status_line.split(" ", 2)
        if len(parts) < 2:
            print("[HTTP ERROR] Respuesta inválida:", status_line.strip())
            return None
            
        status_code = int(parts[1])
        if not (200 <= status_code < 300):
            print("[HTTP ERROR] Servidor respondió con código:", status_code)
            return None
            
        # 7. Procesar según método
        print("[HTTP DEBUG] Descartando cabeceras de respuesta...")
        # Saltar headers línea por línea (sin almacenarlos en memoria)
        headers_count = 0
        while True:
            line = s.readline()
            if not line or line == b"\r\n":
                break
            headers_count += 1
        print("[HTTP DEBUG] Descartados {} headers. Leyendo cuerpo de respuesta...".format(headers_count))
        
        # Leer el body completo (HTTP/1.0 garantiza que lee hasta el EOF al cerrar el server)
        body_data = s.read()
        print("[HTTP DEBUG] Cuerpo de respuesta leído: {} bytes. RAM libre: {} bytes".format(len(body_data), gc.mem_free()))
        
        if method == "GET":
            print("[HTTP DEBUG] Decodificando respuesta JSON...")
            try:
                result = json.loads(body_data)
                print("[HTTP DEBUG] JSON decodificado exitosamente.")
                return result
            except Exception as je:
                print("[HTTP ERROR] Fallo al decodificar JSON del body:", je)
                return None
        else:
            # Para POST (telemetría), un código 2xx es éxito, no necesitamos parsear el cuerpo
            print("[HTTP DEBUG] POST request exitoso.")
            return True
            
    except Exception as e:
        print("[HTTP ERROR] Excepción atrapada en _http_request_optimizado:", e)
        return None
    finally:
        print("[HTTP DEBUG] Cerrando socket y liberando recursos...")
        if s:
            try:
                s.close()
                print("[HTTP DEBUG] Socket cerrado.")
            except Exception as ce:
                print("[HTTP DEBUG] Error al cerrar socket:", ce)
        gc.collect()
        print("[HTTP DEBUG] Request finalizado. RAM libre: {} bytes".format(gc.mem_free()))

def enviar_post_directo(url, payload):
    """Realiza una solicitud HTTP POST síncrona y directa (sin cola ni hilos)"""
    return bool(_http_request_optimizado("POST", url, payload))

pulsar_activo = False

def thread_pulsar():
    global pulsar_activo
    import time
    import math
    import hardware
    
    step = 0
    while pulsar_activo:
        # Pulsación gradual senoidal de cian (G y B)
        # Amplitud de 150 a 800 para que varíe de forma visible, pero sin apagarse a 0
        val = int(475 + 325 * math.sin(step * 0.5))
        try:
            hardware.set_color_pwm(0, val, val)
        except:
            pass
        step += 1
        time.sleep_ms(30) # Pulsación rápida y gradual

def iniciar_pulsacion():
    global pulsar_activo
    pulsar_activo = True
    try:
        import _thread
        _thread.stack_size(4096) # Pila mínima necesaria
        _thread.start_new_thread(thread_pulsar, ())
        _thread.stack_size(0)
    except Exception as e:
        print("[SYNC LED WARNING] No se pudo iniciar pulsación:", e)

def detener_pulsacion():
    global pulsar_activo
    pulsar_activo = False
    import time
    time.sleep_ms(50)
    try:
        import hardware
        hardware.set_color_pwm(0, 0, 0)
    except:
        pass

def sincronizar_config():
    """Descarga e impone la configuración horaria de la Base de Datos centralizada en 3D-Moai"""
    global last_sync_time
    import gc
    import time
    
    # Si sincronizamos hace menos de 60 segundos, omitir para no agotar la memoria del sistema
    ahora = time.ticks_ms()
    if last_sync_time > 0 and time.ticks_diff(ahora, last_sync_time) < 60000:
        print("[SYNC INFO] Sincronización reciente omitida (usando config local).")
        return
        
    iniciar_pulsacion()
    gc.collect()
    gc.collect()
    ram_libre = gc.mem_free()
    
    url = SERVER_URL + "/api/pomodoro/config?device_id=" + DEVICE_ID
    print("[SYNC] Descargando última configuración de 3D-Moai desde {} (RAM libre: {} bytes)...".format(url, ram_libre))
    
    data = _http_request_optimizado("GET", url)
    if data:
        last_sync_time = ahora
        try:
            global tiempo_focus_s, tiempo_descanso_corto_s, tiempo_descanso_largo_s, descanso_largo_activo, ciclos_para_descanso_largo
            tiempo_focus_s = int(data.get("tiempo_focus", tiempo_focus_s))
            tiempo_descanso_corto_s = int(data.get("tiempo_descanso_corto", tiempo_descanso_corto_s))
            tiempo_descanso_largo_s = int(data.get("tiempo_descanso_largo", tiempo_descanso_largo_s))
            descanso_largo_activo = bool(data.get("descanso_largo_activo", descanso_largo_activo))
            ciclos_para_descanso_largo = int(data.get("ciclos_para_descanso_largo", ciclos_para_descanso_largo))
            guardar_a_disco()
            print("[SYNC SUCCESS] Configuración de tiempos sincronizada con 3D-Moai.")
            print_configuracion_actual()
        except Exception as e:
            print("[SYNC ERROR] Fallo al procesar la configuración descargada:", e)
    else:
        print("[SYNC WARNING] No se pudo obtener la configuración desde la nube.")
        
    detener_pulsacion()

def encolar_telemetria(url, payload):
    """Realiza la solicitud HTTP POST de forma síncrona en el hilo principal para evitar ENOMEM en hilos"""
    import gc
    
    # 1. Iniciar animación de sincronización (pulsación cian rápido)
    iniciar_pulsacion()
    
    print("[TELEMETRY] Enviando reporte de estadísticas a:", url)
    intento = 0
    exito = False
    while intento < 2 and not exito:
        try:
            print("[TELEMETRY DEBUG] Iniciando intento síncrono {}/2...".format(intento + 1))
            exito = _http_request_optimizado("POST", url, payload)
            if exito:
                print("[TELEMETRY SUCCESS] Reporte enviado correctamente.")
            else:
                print("[TELEMETRY WARNING] Intento {} de envío síncrono falló.".format(intento + 1))
        except Exception as e:
            print("[TELEMETRY ERROR] Intento {} fallido con excepción: {}".format(intento + 1, e))
        intento += 1
        if not exito and intento < 2:
            import time
            time.sleep_ms(500)
            
    # 2. Detener animación de sincronización
    detener_pulsacion()
    
    gc.collect()
    return exito

def enviar_reporte_pausa(fase, tiempo_transcurrido_s, porcentaje, duracion_pausa_s):
    try:
        url = SERVER_URL + "/api/pomodoro/stats"
        payload = {
            "device_id": DEVICE_ID,
            "tipo_sesion": "pausa_" + fase.lower(),
            "ciclo_num": tiempo_transcurrido_s,
            "duracion_s": duracion_pausa_s,
            "forzado": 0
        }
        encolar_telemetria(url, payload)
    except Exception as e:
        print("[REPORT PAUSE WARNING] No se pudo encolar reporte de pausa:", e)

def enviar_reporte_reaccion(tipo_alerta, duracion_alerta_s):
    try:
        url = SERVER_URL + "/api/pomodoro/stats"
        payload = {
            "device_id": DEVICE_ID,
            "tipo_sesion": "reaccion_" + tipo_alerta.lower(),
            "ciclo_num": 0,
            "duracion_s": int(duracion_alerta_s),
            "forzado": 0
        }
        encolar_telemetria(url, payload)
    except Exception as e:
        print("[REPORT REACTION WARNING] No se pudo encolar reporte de reacción:", e)



# ==============================================================================
# AUTO-EJECUCIÓN AL CARGAR EL MÓDULO
# ==============================================================================
# MicroPython ejecuta estas funciones en cascada al importar 'config'
# garantizando que los datos actualizados estén disponibles desde el inicio.
cargar_de_disco()
cargar_wifi()

