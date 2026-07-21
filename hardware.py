import time
from machine import Pin, PWM
import config

# --- INICIALIZACIÓN DE COMPONENTES DE HARDWARE ---
btn_start = Pin(config.PIN_BTN, Pin.IN, Pin.PULL_UP)

led_rojo = PWM(Pin(config.PIN_LED_ROJO), freq=config.PWM_FREQ_LED)
led_verde = PWM(Pin(config.PIN_LED_VERDE), freq=config.PWM_FREQ_LED)
led_azul = PWM(Pin(config.PIN_LED_AZUL), freq=config.PWM_FREQ_LED)

buzzer = PWM(Pin(config.PIN_BUZZER))
buzzer.duty(0)

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

def reproducir_pitidos(frecuencia, repeticiones=2, duracion_ms=70, pausa_ms=50):
    """Emite impulsos sonoros amigables y audibles"""
    for i in range(repeticiones):
        sonar_buzzer(frecuencia, True)
        time.sleep_ms(duracion_ms)
        sonar_buzzer(0, False)
        if i < repeticiones - 1:
            time.sleep_ms(pausa_ms)

def calcular_intensidad_progresiva(tiempo_transcurrido, tiempo_total_ms):
    """Calcula la intensidad desde el piso tenue (1%) hasta el máximo (100%)"""
    if tiempo_total_ms <= 0:
        return config.DUTY_MAX
    progreso = min(max(tiempo_transcurrido / tiempo_total_ms, 0.0), 1.0)
    intensidad = config.DUTY_PISO + progreso * (config.DUTY_MAX - config.DUTY_PISO)
    return int(intensidad)

def boton_presionado():
    """Retorna True si el botón está presionado (lógica PULL_UP activa en 0)"""
    return btn_start.value() == 0
