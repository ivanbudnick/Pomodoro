# --- CONFIGURACIÓN DE WIFI ---
WIFI_SSID = "TU_RED_WIFI"        # Cambia por el nombre de tu red WiFi
WIFI_PASSWORD = "TU_PASSWORD"     # Cambia por tu contraseña de WiFi

# --- CONFIGURACIÓN DE PINES (ESP32 REAL) ---
PIN_BTN = 23
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

# --- FRECUENCIAS DEL BUZZER (Hz - Notas Armónicas y Suaves) ---
FREQ_BUZZER_INICIO = 523        # Nota Do5 (C5) - Impulso claro para el arranque (Rojo)
FREQ_BUZZER_CAMBIO_ESTADO = 659  # Nota Mi5 (E5) - 2 pitidos amigables fin de Rojo / inicio de Azul
FREQ_BUZZER_TRANSICION = 784    # Nota Sol5 (G5) - Fin de Azul
FREQ_BUZZER_ALERTA = 523         # Nota Do5 (C5) - Pitido corto sutil al titilar

# --- DURACIONES CONFIGURABLES DINÁMICAS (EN SEGUNDOS) ---
tiempo_rojo_s = 5  # Duración del LED en Rojo (configurable vía web)
tiempo_azul_s = 3  # Duración del LED en Azul (configurable vía web)
