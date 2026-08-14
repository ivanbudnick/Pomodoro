# ==============================================================================
# CONFIGURACIÓN GENERAL DEL POMODORO PRO
# ==============================================================================
# Este archivo centraliza todas las constantes del hardware, parámetros del
# temporizador Pomodoro, y rutinas de persistencia local en la Flash del ESP32.
#
# Al ser MicroPython, las variables globales aquí definidas pueden ser modificadas
# en tiempo de ejecución (por ejemplo, desde el servidor web) y guardadas
# de forma persistente.

# --- CONFIGURACIÓN DE WIFI Y SERVIDOR FLASK ---
WIFI_SSID = ""            # Nombre de la red WiFi (se carga de wifi.json)
WIFI_PASSWORD = ""        # Contraseña de la red WiFi (se carga de wifi.json)
DEFAULT_FLASK_SERVER_URL = "https://pomodoro-mocha-one.vercel.app/datos"  # URL predeterminada en la nube/PC
FLASK_SERVER_URL = DEFAULT_FLASK_SERVER_URL  # Endpoint REST en la PC/nube
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC_SESIONES = "pomodoro/sesiones"
VERSION = "1.0.1"
rtc_sincronizado = False

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
    Esto permite que los cambios realizados vía HTTP persistan
    a pesar de reinicios o cortes de energía.
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
                "flask_server_url": FLASK_SERVER_URL,
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
    Si el archivo no existe (por ejemplo, en el primer encendido), se mantiene
    con los valores predeterminados definidos arriba.
    """
    global tiempo_focus_s, tiempo_descanso_corto_s, tiempo_descanso_largo_s, descanso_largo_activo, ciclos_para_descanso_largo, FLASK_SERVER_URL, OTA_GITHUB_USER, OTA_GITHUB_REPO, OTA_GITHUB_BRANCH
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
            
            saved_url = data.get("flask_server_url", FLASK_SERVER_URL)
            # Detección de migración: si la URL por defecto es remota (no local) y la guardada es local (ej. 192.168.x.x),
            # forzamos la actualización al valor por defecto (migración a Vercel)
            is_default_remote = "https://" in DEFAULT_FLASK_SERVER_URL or not ("192.168." in DEFAULT_FLASK_SERVER_URL or "10." in DEFAULT_FLASK_SERVER_URL or "172." in DEFAULT_FLASK_SERVER_URL or "localhost" in DEFAULT_FLASK_SERVER_URL)
            is_saved_local = "192.168." in saved_url or "10." in saved_url or "172." in saved_url or "localhost" in saved_url
            
            if is_default_remote and is_saved_local:
                print("[CONFIG] Detectada migración a servidor de la nube (Vercel). Ignorando IP local obsoleta de config.json.")
                FLASK_SERVER_URL = DEFAULT_FLASK_SERVER_URL
                debe_guardar = True
            else:
                FLASK_SERVER_URL = saved_url
                
            OTA_GITHUB_USER = data.get("ota_github_user", OTA_GITHUB_USER)
            OTA_GITHUB_REPO = data.get("ota_github_repo", OTA_GITHUB_REPO)
            OTA_GITHUB_BRANCH = data.get("ota_github_branch", OTA_GITHUB_BRANCH)
            
        if debe_guardar:
            guardar_a_disco()
            
        print("[CONFIG SUCCESS] Configuración cargada desde config.json local.")
    except Exception as e:
        print("[CONFIG ERROR] Fallo al leer config.json local:", e)

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

def descubrir_servidor_pc():
    """
    Intenta descubrir la dirección IP del servidor Flask en la PC
    utilizando un broadcast UDP en la red local.
    """
    global FLASK_SERVER_URL
    # Si la URL del servidor es una URL de la nube (HTTPS o dominio externo),
    # omitir la búsqueda local para evitar demoras innecesarias por timeout.
    is_remote = "https://" in FLASK_SERVER_URL or not ("192.168." in FLASK_SERVER_URL or "10." in FLASK_SERVER_URL or "172." in FLASK_SERVER_URL or "localhost" in FLASK_SERVER_URL)
    if is_remote:
        return False

    import socket
    import gc
    import network
    
    print("[DISCOVERY] Buscando servidor en la red local...")
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        return False
        
    try:
        # Crear socket UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        # Intentar habilitar broadcast (SO_BROADCAST es 0x0020 en lwIP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, 0x0020, 1)
        except:
            pass
            
        # Enviar mensaje de descubrimiento al puerto 5002
        sock.sendto(b"POMODORO_DISCOVER", ("255.255.255.255", 5002))
        
        # Enviar también al broadcast de la subred para mayor compatibilidad
        try:
            ip_info = wlan.ifconfig()
            ip = ip_info[0]
            parts = ip.split('.')
            if len(parts) == 4:
                subnet_broadcast = "{}.{}.{}.255".format(parts[0], parts[1], parts[2])
                sock.sendto(b"POMODORO_DISCOVER", (subnet_broadcast, 5002))
        except:
            pass
            
        # Esperar respuesta
        data, addr = sock.recvfrom(1024)
        msg = data.decode('utf-8').split(':')
        if msg[0] == "POMODORO_RESPONSE":
            pc_ip = addr[0]
            port = msg[1] if len(msg) > 1 else "5001"
            
            old_url = FLASK_SERVER_URL
            FLASK_SERVER_URL = "http://{}:{}/datos".format(pc_ip, port)
            
            print("[DISCOVERY SUCCESS] ¡Servidor encontrado en {}!".format(pc_ip))
            if old_url != FLASK_SERVER_URL:
                print("[DISCOVERY] URL del servidor actualizada a: {}".format(FLASK_SERVER_URL))
                guardar_a_disco()
            sock.close()
            return True
    except Exception as e:
        print("[DISCOVERY INFO] No se pudo encontrar el servidor automáticamente ({}). Usando fallback.".format(e))
    finally:
        try:
            sock.close()
        except:
            pass
        gc.collect()
        
    return False

def obtener_timestamp():
    """
    Retorna la fecha y hora actual del RTC local del ESP32
    en formato legible para SQLite: YYYY-MM-DD HH:MM:SS.
    """
    try:
        import time
        t = time.localtime()
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])
    except Exception as e:
        print("[RTC WARNING] No se pudo obtener la hora del RTC:", e)
        return "2000-01-01 00:00:00"

def enviar_post_directo(url, payload):
    """Realiza una solicitud HTTP POST síncrona y directa (sin cola ni hilos)"""
    try:
        import urequests
    except ImportError:
        print("[HTTP ERROR] Módulo urequests no disponible.")
        return False
        
    if "timestamp" not in payload:
        payload["timestamp"] = obtener_timestamp()
    if "sync" not in payload:
        payload["sync"] = rtc_sincronizado
        
    res = None
    try:
        import gc
        gc.collect()
        print("[HTTP POST] Enviando datos a:", url)
        res = urequests.post(url, json=payload, timeout=3)
        status = res.status_code
        res.close()
        return 200 <= status < 300
    except Exception as e:
        print("[HTTP ERROR] Fallo al enviar POST directo:", e)
        if res:
            try:
                res.close()
            except:
                pass
        return False

def sincronizar_hora_ntp():
    """Intenta sincronizar la hora usando un servidor NTP de internet"""
    try:
        import ntptime
        print("[NTP] Sincronizando hora con pool.ntp.org...")
        ntptime.host = "pool.ntp.org"
        ntptime.settime()
        global rtc_sincronizado
        rtc_sincronizado = True
        print("[NTP SUCCESS] Reloj RTC sincronizado mediante NTP.")
        return True
    except Exception as e:
        print("[NTP WARNING] No se pudo sincronizar hora por NTP:", e)
        return False

def sincronizar_config_pc():
    """Descarga e impone la configuración horaria de la Base de Datos centralizada (Flask) en la PC"""
    # Intentar descubrir el servidor automáticamente antes de sincronizar
    descubrir_servidor_pc()
    
    try:
        import urequests
    except ImportError:
        urequests = None
        
    if urequests is None:
        print("[SYNC WARNING] Modulo urequests no disponible. Intentando NTP...")
        sincronizar_hora_ntp()
        return
    try:
        import gc
        gc.collect()
        
        url = FLASK_SERVER_URL.replace("/datos", "/api/latest_config")
        print("[SYNC] Descargando última configuración de la PC desde {}...".format(url))
        res = urequests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data:
                global tiempo_focus_s, tiempo_descanso_corto_s, tiempo_descanso_largo_s, descanso_largo_activo, ciclos_para_descanso_largo
                tiempo_focus_s = int(data.get("tiempo_focus", tiempo_focus_s))
                tiempo_descanso_corto_s = int(data.get("tiempo_descanso_corto", tiempo_descanso_corto_s))
                tiempo_descanso_largo_s = int(data.get("tiempo_descanso_largo", tiempo_descanso_largo_s))
                descanso_largo_activo = bool(data.get("descanso_largo_activo", descanso_largo_activo))
                ciclos_para_descanso_largo = int(data.get("ciclos_para_descanso_largo", ciclos_para_descanso_largo))
                guardar_a_disco()
                print("[SYNC SUCCESS] Configuración sincronizada con la base de datos de la PC.")
                
                # Sincronizar el RTC de la ESP32 si viene en el JSON
                server_time = data.get("server_time")
                if server_time:
                    try:
                        import machine
                        rtc = machine.RTC()
                        rtc.datetime(tuple(server_time))
                        global rtc_sincronizado
                        rtc_sincronizado = True
                        print("[SYNC SUCCESS] Reloj RTC sincronizado con el servidor Flask.")
                    except Exception as rtc_err:
                        print("[SYNC WARNING] Fallo al establecer hora RTC desde Flask:", rtc_err)
            else:
                print("[SYNC INFO] No hay configuraciones en la BD de la PC aún.")
        else:
            print("[SYNC WARNING] Servidor Flask no disponible. Intentando NTP...")
            sincronizar_hora_ntp()
        res.close()
    except Exception as e:
        print("[SYNC WARNING] No se pudo conectar a la PC para sincronizar ({}). Intentando NTP...".format(e))
        sincronizar_hora_ntp()
    finally:
        import gc
        gc.collect()

# ==============================================================================
# AUTO-EJECUCIÓN AL CARGAR EL MÓDULO
# ==============================================================================
# MicroPython ejecuta estas funciones en cascada al importar 'config'
# garantizando que los datos actualizados estén disponibles desde el inicio.
cargar_de_disco()
cargar_wifi()

