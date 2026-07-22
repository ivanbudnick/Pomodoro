# --- CONFIGURACIÓN DE WIFI Y SERVIDOR FLASK ---
WIFI_SSID = "El Fi del Wi"            # Red WiFi real
WIFI_PASSWORD = "teamolionelscaloni"  # Contraseña WiFi real
FLASK_SERVER_URL = "http://192.168.0.125:5001/datos"  # Puerto 5001 en PC

# --- CONFIGURACIÓN DE PINES (ESP32 REAL) ---
PIN_BTN = 25                   # Botón 1: Inicio / Reanudación (Cambiado a GPIO 25 para evitar conflicto de cristal de 32kHz en ESP-32S)
PIN_BTN_CONTROL = 22           # Botón 2: Pausa / Gestos (Reset Fase / Reset Standby)
PIN_LED_ROJO = 14
PIN_LED_VERDE = 27
PIN_LED_AZUL = 26
PIN_BUZZER = 13

# --- CONFIGURACIÓN DE PWM ---
PWM_FREQ_LED = 1000
DUTY_MAX = 1023
DUTY_PISO = int(DUTY_MAX / 100)  # ~10 (1% de intensidad tenue)
BUZZER_DUTY = 512

# --- CONSTANTES DE TIEMPO (ms) ---
INTERVALO_TITILO_STANDBY_MS = 500
INTERVALO_ALERTA_MS = 500
TIEMPO_TRANSICION_PITIDO_MS = 100
DEBOUNCE_BOTON_MS = 300
LOOP_SLEEP_MS = 10
TIEMPO_INACTIVIDAD_SLEEP_MS = 5000  # 5 segundos de inactividad para entrar en Deep Sleep (Testing rápido)

# --- CONSTANTES DE GESTOS PARA BOTÓN 2 ---
TIEMPO_MANTENER_STANDBY_MS = 2000  # 2 segundos de presión para volver a Standby
VENTANA_DOBLE_CLIC_MS = 400        # 400 ms de ventana para detectar doble clic

# --- FRECUENCIAS DEL BUZZER (Hz - Notas Armónicas y Suaves) ---
FREQ_BUZZER_INICIO = 523        # Nota Do5 (C5) - Impulso para el inicio del Focus
FREQ_BUZZER_CAMBIO_ESTADO = 659  # Nota Mi5 (E5) - Fin de Focus
FREQ_BUZZER_TRANSICION = 784    # Nota Sol5 (G5) - Fin de Descanso
FREQ_BUZZER_ALERTA = 523         # Nota Do5 (C5) - Destello en Alerta
FREQ_BUZZER_RESET_FASE = 784     # Nota Sol5 (G5) - Tono de reinicio de fase actual
FREQ_BUZZER_IDLE = 440           # Nota La4 (A4) - Tono de retorno a Standby

# --- PARÁMETROS DE POMODORO Y DESCANSO LARGO CONFIGURABLES ---
tiempo_focus_s = 5           # Duración de sesión Focus en segundos
tiempo_descanso_corto_s = 3   # Duración de Descanso Corto en segundos
tiempo_descanso_largo_s = 6   # Duración de Descanso Largo en segundos

descanso_largo_activo = True  # Habilitado / Deshabilitado
ciclos_para_descanso_largo = 4 # Cantidad de sesiones Focus para desencadenar Descanso Largo (mínimo 2)

# --- PERSISTENCIA LOCAL (JSON) EN FLASH DE LA ESP32 ---
def guardar_a_disco():
    """Guarda la configuración actual en un archivo config.json local en el ESP32"""
    try:
        import ujson as json
        with open("config.json", "w") as f:
            json.dump({
                "tiempo_focus": tiempo_focus_s,
                "tiempo_descanso_corto": tiempo_descanso_corto_s,
                "tiempo_descanso_largo": tiempo_descanso_largo_s,
                "descanso_largo_activo": descanso_largo_activo,
                "ciclos_para_descanso_largo": ciclos_para_descanso_largo
            }, f)
        print("[CONFIG] Configuración guardada en config.json local.")
    except Exception as e:
        print("[CONFIG ERROR] No se pudo guardar config.json local:", e)

def cargar_de_disco():
    """Carga la configuración desde config.json local en el ESP32 si existe"""
    global tiempo_focus_s, tiempo_descanso_corto_s, tiempo_descanso_largo_s, descanso_largo_activo, ciclos_para_descanso_largo
    try:
        import os
        import ujson as json
        # Verificar si el archivo existe antes de abrirlo
        try:
            os.stat("config.json")
        except OSError:
            print("[CONFIG INFO] No existe config.json local. Usando valores por defecto.")
            return
            
        with open("config.json", "r") as f:
            data = json.load(f)
            tiempo_focus_s = int(data.get("tiempo_focus", tiempo_focus_s))
            tiempo_descanso_corto_s = int(data.get("tiempo_descanso_corto", tiempo_descanso_corto_s))
            tiempo_descanso_largo_s = int(data.get("tiempo_descanso_largo", tiempo_descanso_largo_s))
            descanso_largo_activo = bool(data.get("descanso_largo_activo", descanso_largo_activo))
            ciclos_para_descanso_largo = int(data.get("ciclos_para_descanso_largo", ciclos_para_descanso_largo))
        print("[CONFIG SUCCESS] Configuración cargada desde config.json local.")
    except Exception as e:
        print("[CONFIG ERROR] Fallo al leer config.json local:", e)

# Cargar configuración del disco al importar el módulo
cargar_de_disco()

