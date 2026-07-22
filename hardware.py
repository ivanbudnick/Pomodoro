import time
from machine import Pin, PWM
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

# --- VARIABLES DE ESTADO PARA GESTOS (BOTÓN 2) ---
_last_state = 1
_press_time = 0
_release_time = 0
_click_count = 0
_long_press_triggered = False

# --- FUNCIONES DE CONTROL DE HARDWARE ---
def set_color_pwm(r_duty, g_duty, b_duty):
    """Establece la intensidad de cada canal RGB (0 a 1023)"""
    led_rojo.duty(int(r_duty))
    led_verde.duty(int(g_duty))
    led_azul.duty(int(b_duty))

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
