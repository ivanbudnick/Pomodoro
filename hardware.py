import time
from machine import Pin, PWM, ADC
import config

# --- GESTOS DEL BOTÓN DE CONTROL ---
GESTO_NINGUNO = 0
GESTO_PAUSA = 1
GESTO_RESET_FASE = 2
GESTO_RESET_IDLE = 3

# --- INICIALIZACIÓN DE COMPONENTES DE HARDWARE ---
btn_start = Pin(config.PIN_BTN, Pin.IN, Pin.PULL_UP)
btn_control = Pin(config.PIN_BTN_CONTROL, Pin.IN, Pin.PULL_UP)

led_rojo = PWM(Pin(config.PIN_LED_ROJO), freq=config.PWM_FREQ_LED)
led_verde = PWM(Pin(config.PIN_LED_VERDE), freq=config.PWM_FREQ_LED)
led_azul = PWM(Pin(config.PIN_LED_AZUL), freq=config.PWM_FREQ_LED)

buzzer = PWM(Pin(config.PIN_BUZZER))
buzzer.duty(0)

# --- INICIALIZACIÓN DEL SENSOR LDR (FOTORESISTENCIA) ---
try:
    ldr_adc = ADC(Pin(config.PIN_LDR))
    ldr_adc.atten(ADC.ATTN_11DB)  # Configurar atenuación para rango 0V-3.3V
except Exception as e:
    print("[HARDWARE WARNING] No se pudo inicializar LDR en pin {}: {}".format(config.PIN_LDR, e))
    ldr_adc = None

# --- VARIABLES DE ESTADO PARA GESTOS (BOTÓN 2) ---
_last_state = 1
_press_time = 0
_release_time = 0
_click_count = 0
_long_press_triggered = False
_last_ldr_print = 0

# --- FUNCIONES DE CONTROL DE HARDWARE ---
def leer_factor_brillo_ldr():
    """
    Lee el nivel de luz ambiental desde la LDR y retorna un factor de brillo
    entre config.LDR_MIN_FACTOR y config.LDR_MAX_FACTOR.
    """
    global _last_ldr_print
    if ldr_adc is None:
        return 1.0
    try:
        val = ldr_adc.read()
        # Clampear el valor en el rango esperado
        val_clamped = min(max(val, config.LDR_MIN_VAL), config.LDR_MAX_VAL)
        # Interpolar linealmente entre el rango ADC y el rango de factor
        rango_adc = config.LDR_MAX_VAL - config.LDR_MIN_VAL
        rango_factor = config.LDR_MAX_FACTOR - config.LDR_MIN_FACTOR
        if rango_adc <= 0:
            factor = config.LDR_MAX_FACTOR
        else:
            factor = config.LDR_MIN_FACTOR + ((val_clamped - config.LDR_MIN_VAL) / rango_adc) * rango_factor
        
        # Printear constantemente cada 1 segundo (1000 ms) para no inundar la consola
        ahora = time.ticks_ms()
        if time.ticks_diff(ahora, _last_ldr_print) >= 1000:
            print("[LDR] ADC Raw: {} | Brillo LEDs: {:.1f}%".format(val, factor * 100))
            _last_ldr_print = ahora
            
        return factor
    except Exception as e:
        print("[HARDWARE ERROR] Fallo al leer LDR:", e)
        return 1.0

def set_color_pwm(r_duty, g_duty, b_duty):
    """Establece la intensidad de cada canal RGB (0 a 1023) escalado según la luz ambiental (LDR)"""
    factor = leer_factor_brillo_ldr()
    led_rojo.duty(int(r_duty * factor))
    led_verde.duty(int(g_duty * factor))
    led_azul.duty(int(b_duty * factor))

def sonar_buzzer(frecuencia, encendido):
    """Controla el encendido y frecuencia del buzzer"""
    if encendido:
        buzzer.freq(frecuencia)
        buzzer.duty(config.BUZZER_DUTY)
    else:
        buzzer.duty(0)


def calcular_intensidad_progresiva(tiempo_transcurrido, tiempo_total_ms):
    """
    Calcula la intensidad utilizando una curva exponencial suave cuadrática (t^2).
    Comienza creciendo despacio al inicio y acelera progresivamente hacia el final.
    """
    if tiempo_total_ms <= 0:
        return config.DUTY_MAX
    progreso_lineal = min(max(tiempo_transcurrido / tiempo_total_ms, 0.0), 1.0)
    # Curva exponencial cuadrática para respuesta visual cinemática en el ojo humano
    progreso_exp = progreso_lineal * progreso_lineal
    intensidad = config.DUTY_PISO + progreso_exp * (config.DUTY_MAX - config.DUTY_PISO)
    return int(intensidad)

def boton_presionado():
    """Retorna True si el botón de inicio está presionado (lógica PULL_UP activa en 0)"""
    return btn_start.value() == 0

def detectar_gesto_boton_control():
    """
    Escanea de forma no bloqueante el estado del botón GPIO 22 y retorna el gesto detectado.
    Distingue: Clic simple (Pausa), Doble clic (Reset Fase), Mantener 2 segundos (Reset Idle).
    """
    global _last_state, _press_time, _release_time, _click_count, _long_press_triggered
    
    ahora = time.ticks_ms()
    estado_actual = btn_control.value()
    gesto = GESTO_NINGUNO
    
    # 1. Detección de presión inicial (Transición de 1 -> 0)
    if _last_state == 1 and estado_actual == 0:
        _press_time = ahora
        _long_press_triggered = False
        time.sleep_ms(15) # Anti-rebote
        
    # 2. Detección de liberación (Transición de 0 -> 1)
    elif _last_state == 0 and estado_actual == 1:
        time.sleep_ms(15) # Anti-rebote
        if not _long_press_triggered:
            _click_count += 1
            _release_time = ahora
            
    # 3. Detección de Mantener Presionado (Long Press - mientras está presionado)
    if estado_actual == 0 and not _long_press_triggered:
        if time.ticks_diff(ahora, _press_time) >= config.TIEMPO_MANTENER_STANDBY_MS:
            _long_press_triggered = True
            _click_count = 0
            gesto = GESTO_RESET_IDLE
            
    # 4. Procesamiento del clic acumulado tras expirar la ventana de doble clic
    if _click_count > 0 and estado_actual == 1:
        if time.ticks_diff(ahora, _release_time) >= config.VENTANA_DOBLE_CLIC_MS:
            if _click_count == 1:
                gesto = GESTO_PAUSA
            elif _click_count >= 2:
                gesto = GESTO_RESET_FASE
            _click_count = 0
            
    _last_state = estado_actual
    return gesto
