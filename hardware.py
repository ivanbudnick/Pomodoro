# ==============================================================================
# CONTROLADORES DE HARDWARE - DRIVERS DE DISPOSITIVOS
# ==============================================================================
# Este módulo inicializa y controla los periféricos físicos conectados al ESP32:
# 1. LED RGB (mediante señales PWM) regulados según luz ambiental.
# 2. Buzzer piezoeléctrico pasivo (tonos PWM).
# 3. Sensor fotoresistor LDR (ADC).
# 4. Display de 7 segmentos de 4 dígitos (con registro de desplazamiento 74HC595).
# 5. Lógica de debounce y detección de gestos por software para botones de entrada.

import time
from machine import Pin, PWM, ADC, Timer, SoftSPI
import config

# --- GESTOS DEL BOTÓN DE CONTROL ---
# Códigos de retorno para simplificar la máquina de estados en pomodoro.py
GESTO_NINGUNO = 0
GESTO_PAUSA = 1
GESTO_RESET_FASE = 2
GESTO_RESET_IDLE = 3

# --- INICIALIZACIÓN DE COMPONENTES DE HARDWARE ---
# Los botones usan resistencias internas de PULL-UP; retornan 0 al ser pulsados.
btn_start = Pin(config.PIN_BTN, Pin.IN, Pin.PULL_UP)
btn_control = Pin(config.PIN_BTN_CONTROL, Pin.IN, Pin.PULL_UP)

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

# ==============================================================================
# DRIVER DISPLAY 7-SEGMENTOS (74HC595 + MULTIPLEXACIÓN)
# ==============================================================================
# Para mostrar 4 dígitos usando pocos pines del ESP32, se implementan dos técnicas:
# 1. Registro de Desplazamiento 74HC595: Recibe el patrón de 8 bits de forma serial
#    (un bit a la vez pulsando SH_CP) y lo expone en paralelo al display (pulsando ST_CP).
# 2. Multiplexación por Tiempo: Se enciende un único dígito a la vez a muy alta velocidad.
#    El ojo humano experimenta 'persistencia visual' y percibe los 4 dígitos encendidos a la vez.
#
# Para evitar sombras o 'efecto fantasma', se apagan todos los dígitos antes de enviar
# los datos del siguiente dígito.
class Display7Segment:
    # Mapeo de bits de segmentos para números 0-9 (Cátodo Común)
    # Bits representados en orden: dp - g - f - e - d - c - b - a
    NUMEROS = [
        0b00111111, # 0
        0b00000110, # 1
        0b01011011, # 2
        0b01001111, # 3
        0b01100110, # 4
        0b01101101, # 5
        0b01111101, # 6
        0b00000111, # 7
        0b01111111, # 8
        0b01101111  # 9
    ]
    
    def __init__(self, ds, sh_cp, st_cp, dig1, dig2, dig3, dig4):
        self.st_cp = Pin(st_cp, Pin.OUT)
        self.st_cp.on()
        
        self.digitos = [
            Pin(dig1, Pin.OUT),
            Pin(dig2, Pin.OUT),
            Pin(dig3, Pin.OUT),
            Pin(dig4, Pin.OUT)
        ]
        self.apagar_digitos()
        self.buffer = [0, 0, 0, 0]  # Buffer de patrones a mostrar en cada dígito [D1, D2, D3, D4]
        self.activo = 0             # Índice del dígito actualmente iluminado
        self.timer = Timer(0)       # Hardware Timer 0 de MicroPython para multiplexación asíncrona
        
        # SoftSPI: mosi es serial data (DS), sck es shift clock (SH_CP), miso es dummy (GPIO 35)
        # Esto delega el desplazamiento de bits al hardware optimizado en C, reduciendo el delay de 250us a 15us.
        self.spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(sh_cp), mosi=Pin(ds), miso=Pin(35, Pin.IN))
        
    def apagar_digitos(self):
        """Apaga los 4 transistores/selectores de los dígitos (cátodo común = HIGH es apagado)"""
        for d in self.digitos:
            d.value(1)
            
    def enviar_byte(self, data):
        """Envía serialmente un byte al 74HC595 utilizando hardware SoftSPI acelerado por C"""
        self.st_cp.off()
        self.spi.write(bytearray([data]))
        self.st_cp.on()
        
    def refrescar(self, timer_obj):
        """
        Callback periódico invocado en segundo plano por el Timer por hardware.
        Multiplexa secuencialmente cada uno de los 4 dígitos.
        """
        self.apagar_digitos()
        self.enviar_byte(self.buffer[self.activo])
        self.digitos[self.activo].value(0)  # LOW enciende el cátodo común del dígito activo
        self.activo = (self.activo + 1) % 4
        
    def iniciar(self):
        """Inicia el temporizador periódico a 5ms (~200Hz globales, 50Hz por dígito sin parpadeo)"""
        self.timer.init(period=5, mode=Timer.PERIODIC, callback=self.refrescar)
        
    def detener(self):
        """Detiene el temporizador y limpia los pines para ahorrar energía"""
        self.timer.deinit()
        self.apagar_digitos()
        
    def mostrar_tiempo(self, remaining_s, parpadear_punto=True):
        """Muestra los minutos y segundos en formato clásico MM:SS"""
        mins = remaining_s // 60
        secs = remaining_s % 60
        
        d1 = mins // 10
        d2 = mins % 10
        d3 = secs // 10
        d4 = secs % 10
        
        self.buffer[0] = self.NUMEROS[d1]
        
        # Parpadeo del punto decimal (dp en bit 7) para indicar actividad del reloj
        dp_on = parpadear_punto and (remaining_s % 2 == 0)
        self.buffer[1] = self.NUMEROS[d2] | (0x80 if dp_on else 0)
        
        self.buffer[2] = self.NUMEROS[d3]
        self.buffer[3] = self.NUMEROS[d4]
        
    def mostrar_pomodoro(self, remaining_s, ciclos_focus, ocultar_vueltas=False):
        """
        Formatea el display para el modo Pomodoro Pro:
        - Dígito 1: Número de vueltas (sesiones focus) restantes para el descanso largo.
        - Dígito 2: Apagado (separador visual).
        - Dígitos 3 y 4: Minutos restantes (o segundos si queda menos de un minuto).
        """
        # Calcular vueltas restantes para el descanso largo
        if config.descanso_largo_activo and not ocultar_vueltas:
            target = max(2, config.ciclos_para_descanso_largo)
            vueltas_restantes = target - (ciclos_focus % target)
            if vueltas_restantes >= 10:
                decenas = (vueltas_restantes // 10) % 10
                unidades = vueltas_restantes % 10
                self.buffer[0] = self.NUMEROS[decenas]
                self.buffer[1] = self.NUMEROS[unidades]
            elif 0 <= vueltas_restantes < 10:
                self.buffer[0] = self.NUMEROS[vueltas_restantes]
                self.buffer[1] = 0b00000000  # Apagado
            else:
                self.buffer[0] = 0b01000000  # Guión '-' para imprevistos
                self.buffer[1] = 0b00000000
        else:
            self.buffer[0] = 0b00000000  # Vacío
            self.buffer[1] = 0b00000000  # Vacío
        
        # Mostrar tiempo en dígitos 3 y 4 (cambia a segundos si es menor a 1 minuto)
        mins = remaining_s // 60
        if mins >= 1:
            d3 = mins // 10
            d4 = mins % 10
        else:
            d3 = remaining_s // 10
            d4 = remaining_s % 10
            
        self.buffer[2] = self.NUMEROS[d3]
        self.buffer[3] = self.NUMEROS[d4]
        
    def limpiar(self):
        """Limpia el buffer apagando todos los dígitos"""
        self.buffer = [0, 0, 0, 0]
        
    def mostrar_texto(self, texto):
        """Traduce caracteres alfabéticos simples a patrones de 7 segmentos"""
        CHAR_MAP = {
            ' ': 0b00000000,
            '-': 0b01000000,
            '_': 0b00001000,
            '0': 0b00111111, '1': 0b00000110, '2': 0b01011011, '3': 0b01001111,
            '4': 0b01100110, '5': 0b01101101, '6': 0b01111101, '7': 0b00000111,
            '8': 0b01111111, '9': 0b01101111,
            'a': 0b01011111, 'A': 0b01110111,
            'b': 0b01111100, 'B': 0b01111111,
            'c': 0b01011000, 'C': 0b00111001,
            'd': 0b01011110, 'D': 0b00111111,
            'e': 0b01111011, 'E': 0b01111001,
            'f': 0b01110001, 'F': 0b01110001,
            'g': 0b01101111, 'G': 0b00111101,
            'h': 0b01110100, 'H': 0b01110110,
            'i': 0b00010000, 'I': 0b00110000,
            'j': 0b00001110, 'J': 0b00011110,
            'l': 0b00111000, 'L': 0b00111000,
            'n': 0b01010100, 'N': 0b00110111,
            'o': 0b01011100, 'O': 0b00111111,
            'p': 0b01110011, 'P': 0b01110011,
            'r': 0b01010000, 'R': 0b01110111,
            's': 0b01101101, 'S': 0b01101101,
            't': 0b01111000, 'T': 0b00110001,
            'u': 0b00011100, 'U': 0b00111110,
            'y': 0b01101110, 'Y': 0b01101110,
        }
        texto = (texto + "    ")[:4]
        for i in range(4):
            char = texto[i]
            self.buffer[i] = CHAR_MAP.get(char, CHAR_MAP.get(char.lower(), 0))

# --- INSTANCIACIÓN DEL DISPLAY ---
display = Display7Segment(
    ds=config.PIN_74HC595_DS,
    sh_cp=config.PIN_74HC595_SH_CP,
    st_cp=config.PIN_74HC595_ST_CP,
    dig1=config.PIN_DISPLAY_DIG1,
    dig2=config.PIN_DISPLAY_DIG2,
    dig3=config.PIN_DISPLAY_DIG3,
    dig4=config.PIN_DISPLAY_DIG4
)
display.iniciar()

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
    """Retorna True si el botón físico de inicio/despertar (GPIO 25) está pulsado"""
    return btn_start.value() == 0

def detectar_gesto_boton_control():
    """
    Escanea en cada ciclo de loop el estado físico del Botón 2 (GPIO 22).
    Utiliza marcas de tiempo no bloqueantes para diferenciar tres gestos:
    1. Clic simple (retorna GESTO_PAUSA): Un clic rápido.
    2. Clic doble (retorna GESTO_RESET_FASE): Dos pulsaciones en menos de 400ms.
    3. Presión larga (retorna GESTO_RESET_IDLE): Botón pulsado continuamente por más de 2 segundos.
    """
    global _last_state, _press_time, _release_time, _click_count, _long_press_triggered
    
    ahora = time.ticks_ms()
    estado_actual = btn_control.value()
    gesto = GESTO_NINGUNO
    
    # Transición 1 -> 0 (Botón Presionado)
    if _last_state == 1 and estado_actual == 0:
        _press_time = ahora
        _long_press_triggered = False
        time.sleep_ms(15)  # Anti-rebote por hardware por software básico (15ms)
        
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
            elif _click_count >= 2:
                gesto = GESTO_RESET_FASE
            _click_count = 0
            
    _last_state = estado_actual
    return gesto

def check_pairing_requested():
    """Retorna True si ambos botones físicos están presionados simultáneamente"""
    return btn_start.value() == 0 and btn_control.value() == 0

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



