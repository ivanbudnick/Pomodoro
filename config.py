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
DEFAULT_SERVER_URL = "https://pomodoro-mocha-one.vercel.app"  # URL predeterminada en la nube
SERVER_URL = DEFAULT_SERVER_URL  # Base URL del servidor en la nube
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC_SESIONES = "pomodoro/sesiones"
try:
    from version import VERSION
except ImportError:
    VERSION = "1.0.1"

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
                
            SERVER_URL = saved_url
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

# Cola de telemetría asíncrona en memoria
telemetria_cola = []
import _thread
cola_lock = _thread.allocate_lock()
worker_iniciado = False

def encolar_telemetria(url, payload):
    """Agrega un reporte a la cola en memoria para envío asíncrono y arranca el worker si no está activo"""
    global worker_iniciado
    
    with cola_lock:
        if len(telemetria_cola) < 50:
            telemetria_cola.append((url, payload))
        else:
            print("[TELEMETRY WARNING] Cola llena. Descartando reporte antiguo.")
            telemetria_cola.pop(0)
            telemetria_cola.append((url, payload))
            
    if not worker_iniciado:
        try:
            _thread.start_new_thread(_telemetry_worker, ())
            worker_iniciado = True
        except Exception as e:
            print("[TELEMETRY ERROR] No se pudo iniciar el hilo asíncrono:", e)

def _telemetry_worker():
    """Bucle del hilo de fondo que procesa la cola de telemetría secuencialmente"""
    global worker_iniciado
    
    import urequests
    import gc
    import time
    
    while True:
        item = None
        with cola_lock:
            if len(telemetria_cola) > 0:
                item = telemetria_cola.pop(0)
                
        if item is not None:
            url, payload = item
            intento = 0
            exito = False
            while intento < 2 and not exito:
                res = None
                try:
                    gc.collect()
                    res = urequests.post(url, json=payload, timeout=5)
                    if 200 <= res.status_code < 300:
                        exito = True
                    res.close()
                except Exception as e:
                    if res:
                        try:
                            res.close()
                        except:
                            pass
                intento += 1
                if not exito:
                    time.sleep_ms(500)
            
            # Recolectar basura tras cada envío asíncrono
            gc.collect()
        else:
            time.sleep_ms(500)

def enviar_reporte_pausa(fase, tiempo_transcurrido_s, porcentaje, duracion_pausa_s):
    try:
        url = SERVER_URL + "/api/registro_pausa"
        payload = {
            "fase": fase,
            "tiempo_transcurrido_s": tiempo_transcurrido_s,
            "porcentaje_transcurrido": porcentaje,
            "duracion_pausa_s": duracion_pausa_s
        }
        encolar_telemetria(url, payload)
    except Exception as e:
        print("[REPORT PAUSE WARNING] No se pudo encolar reporte de pausa:", e)

def enviar_reporte_reaccion(tipo_alerta, duracion_alerta_s):
    try:
        url = SERVER_URL + "/api/registro_reaccion"
        payload = {
            "tipo_alerta": tipo_alerta,
            "duracion_alerta_s": duracion_alerta_s
        }
        encolar_telemetria(url, payload)
    except Exception as e:
        print("[REPORT REACTION WARNING] No se pudo encolar reporte de reacción:", e)

def enviar_reporte_ciclo(fase, evento, tiempo_activo_s, forzado=0):
    try:
        url = SERVER_URL + "/api/registro_ciclo"
        payload = {
            "fase": fase,
            "evento": evento,
            "tiempo_activo_s": tiempo_activo_s,
            "forzado": forzado
        }
        encolar_telemetria(url, payload)
    except Exception as e:
        print("[REPORT CYCLE WARNING] No se pudo encolar reporte de ciclo:", e)

# ==============================================================================
# AUTO-EJECUCIÓN AL CARGAR EL MÓDULO
# ==============================================================================
# MicroPython ejecuta estas funciones en cascada al importar 'config'
# garantizando que los datos actualizados estén disponibles desde el inicio.
cargar_de_disco()
cargar_wifi()

