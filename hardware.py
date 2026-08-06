# ==============================================================================
# CONTROLADORES DE HARDWARE - DRIVERS DE DISPOSITIVOS
# ==============================================================================
# Este módulo inicializa y controla los periféricos físicos conectados al ESP32:
# 1. LED RGB (mediante señales PWM) regulados según luz ambiental.
# 2. Buzzer piezoeléctrico pasivo (tonos PWM).
# 3. Sensor fotoresistor LDR (ADC).
# 4. Lógica de debounce y detección de gestos por software para botones de entrada.

import time
from machine import Pin, PWM, ADC
import config

# --- GESTOS DEL BOTÓN DE CONTROL ---
# Códigos de retorno para simplificar la máquina de estados en pomodoro.py
GESTO_NINGUNO = 0
GESTO_PAUSA = 1
GESTO_RESET_FASE = 2
GESTO_RESET_IDLE = 3
GESTO_AVANCE_FORZADO = 4

# --- INICIALIZACIÓN DE COMPONENTES DE HARDWARE ---
# El botón único usa resistencia interna de PULL-UP; retorna 0 al ser pulsado.
btn_unico = Pin(config.PIN_BTN, Pin.IN, Pin.PULL_UP)

# Configuración PWM para los canales del LED RGB para regular su ciclo de trabajo (brillo)
led_rojo = PWM(Pin(config.PIN_LED_ROJO), freq=config.PWM_FREQ_LED)
led_verde = PWM(Pin(config.PIN_LED_VERDE), freq=config.PWM_FREQ_LED)
led_azul = PWM(Pin(config.PIN_LED_AZUL), freq=config.PWM_FREQ_LED)

# Configuración PWM para el Zumbador (Buzzer) pasivo. Se inicializa en ciclo 0 (silencio).
buzzer = PWM(Pin(config.PIN_BUZZER))
buzzer.duty(0)

# Configuración del LED incorporado (interno) de la placa
try:
    led_interno = Pin(config.PIN_LED_INTERNO, Pin.OUT)
    led_interno.off()
except Exception as e:
    print("[HARDWARE WARNING] No se pudo inicializar LED interno en pin {}: {}".format(config.PIN_LED_INTERNO, e))
    led_interno = None

# --- INICIALIZACIÓN DEL SENSOR LDR (FOTORESISTENCIA) ---
# La atenuación de 11dB en el Conversor Analógico Digital (ADC) permite leer voltajes
# de entrada en el rango completo de 0V a 3.3V (apropiado para el divisor de tensión del LDR).
try:
    ldr_adc = ADC(Pin(config.PIN_LDR))
    ldr_adc.atten(ADC.ATTN_11DB)
except Exception as e:
    print("[HARDWARE WARNING] No se pudo inicializar LDR en pin {}: {}".format(config.PIN_LDR, e))
    ldr_adc = None

# --- VARIABLES DE ESTADO INTERNAS PARA EL BOTÓN DE CONTROL (GESTOS) ---
_last_state = 1               # Último estado lógico del botón (PULL-UP = 1 inactivo)
_press_time = 0               # Marca ticks_ms() en que se pulsó el botón
_release_time = 0             # Marca ticks_ms() en que se soltó el botón
_click_count = 0              # Contador acumulado de clicks en la ventana temporal
_long_press_triggered = False  # Previene segundas detecciones durante una misma pulsación larga

# ==============================================================================
# FUNCIONES DE INTERACCIÓN FÍSICA Y SENSADO
# ==============================================================================

def leer_factor_brillo_ldr():
    """
    Lee el fotoresistor (LDR) a través del ADC y retorna un factor flotante de atenuación.
    - Si hay mucha luz ambiental: El factor es cercano a 1.0 (brillo máximo del LED).
    - En la oscuridad: Retorna LDR_MIN_FACTOR (~0.05) para atenuar el LED al 5%
      y que no encandile ni consuma corriente innecesaria.
    """
    if ldr_adc is None:
        return 1.0
    try:
        val = ldr_adc.read()
        # Clampear la lectura entre los umbrales configurados
        val_clamped = min(max(val, config.LDR_MIN_VAL), config.LDR_MAX_VAL)
        
        rango_adc = config.LDR_MAX_VAL - config.LDR_MIN_VAL
        rango_factor = config.LDR_MAX_FACTOR - config.LDR_MIN_FACTOR
        
        if rango_adc <= 0:
            factor = config.LDR_MAX_FACTOR
        else:
            # Interpolación lineal simple
            factor = config.LDR_MIN_FACTOR + ((val_clamped - config.LDR_MIN_VAL) / rango_adc) * rango_factor
            
        return factor
    except Exception as e:
        print("[HARDWARE ERROR] Fallo al leer LDR:", e)
        return 1.0

def set_color_pwm(r_duty, g_duty, b_duty):
    """Establece la intensidad RGB de forma no bloqueante escalándola por el LDR"""
    factor = leer_factor_brillo_ldr()
    led_rojo.duty(int(r_duty * factor))
    led_verde.duty(int(g_duty * factor))
    led_azul.duty(int(b_duty * factor))

def sonar_buzzer(frecuencia, encendido):
    """
    Activa o silencia el buzzer pasivo.
    - Si encendido es True: Emite una señal PWM con la frecuencia dada y ciclo 512 (50%).
    - Si encendido es False: Ciclo de trabajo 0 (silencio total).
    """
    if encendido:
        buzzer.freq(frecuencia)
        buzzer.duty(config.BUZZER_DUTY)
    else:
        buzzer.duty(0)

def calcular_intensidad_progresiva(tiempo_transcurrido, tiempo_total_ms):
    """
    Calcula una respuesta lumínica cinematográfica basada en una curva cuadrática (t^2).
    La intensidad comienza muy tenue en el piso mínimo (DUTY_PISO) y acelera su brillo
    hacia el final del temporizador, logrando un feedback visual dramático pero cómodo.
    """
    if tiempo_total_ms <= 0:
        return config.DUTY_MAX
    progreso_lineal = min(max(tiempo_transcurrido / tiempo_total_ms, 0.0), 1.0)
    # Curva exponencial cuadrática
    progreso_exp = progreso_lineal * progreso_lineal
    intensidad = config.DUTY_PISO + progreso_exp * (config.DUTY_MAX - config.DUTY_PISO)
    return int(intensidad)

def boton_presionado():
    """Retorna True si el botón único está pulsado"""
    return btn_unico.value() == 0

def detectar_gesto_boton_control():
    """
    Escanea en cada ciclo de loop el estado físico del botón único.
    Utiliza marcas de tiempo no bloqueantes para diferenciar cuatro gestos:
    1. Clic simple (retorna GESTO_PAUSA): Un clic rápido.
    2. Clic doble (retorna GESTO_RESET_FASE): Dos pulsaciones en menos de 400ms.
    3. Clic triple (retorna GESTO_AVANCE_FORZADO): Tres pulsaciones en menos de 400ms.
    4. Presión larga (retorna GESTO_RESET_IDLE): Botón pulsado continuamente por más de 2 segundos.
    """
    global _last_state, _press_time, _release_time, _click_count, _long_press_triggered
    
    ahora = time.ticks_ms()
    estado_actual = btn_unico.value()
    gesto = GESTO_NINGUNO
    
    # Transición 1 -> 0 (Botón Presionado)
    if _last_state == 1 and estado_actual == 0:
        _press_time = ahora
        _long_press_triggered = False
        time.sleep_ms(15)  # Anti-rebote por software básico (15ms)
        
    # Transición 0 -> 1 (Botón Soltado)
    elif _last_state == 0 and estado_actual == 1:
        time.sleep_ms(15)  # Anti-rebote
        if not _long_press_triggered:
            _click_count += 1
            _release_time = ahora
            
    # Detección dinámica de pulsación prolongada (Long Press) mientras el botón sigue presionado
    if estado_actual == 0 and not _long_press_triggered:
        if time.ticks_diff(ahora, _press_time) >= config.TIEMPO_MANTENER_STANDBY_MS:
            _long_press_triggered = True
            _click_count = 0
            gesto = GESTO_RESET_IDLE
            
    # Procesar clics acumulados una vez que expira la ventana de tiempo del doble clic
    if _click_count > 0 and estado_actual == 1:
        if time.ticks_diff(ahora, _release_time) >= config.VENTANA_DOBLE_CLIC_MS:
            if _click_count == 1:
                gesto = GESTO_PAUSA
            elif _click_count == 2:
                gesto = GESTO_RESET_FASE
            elif _click_count >= 3:
                gesto = GESTO_AVANCE_FORZADO
            _click_count = 0
            
    _last_state = estado_actual
    return gesto

def reset_gestos():
    """Resetea las variables internas del detector de gestos para evitar falsos disparos al soltar botones"""
    global _last_state, _press_time, _release_time, _click_count, _long_press_triggered
    _last_state = 1
    _press_time = 0
    _release_time = 0
    _click_count = 0
    _long_press_triggered = False

def set_led_interno(estado):
    """Enciende (True) o apaga (False) el LED interno del ESP32"""
    global led_interno
    if led_interno:
        try:
            led_interno.value(1 if estado else 0)
        except Exception as e:
            print("[HARDWARE ERROR] No se pudo setear LED interno:", e)



