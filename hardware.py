import time
from machine import Pin, PWM, ADC, Timer
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

# --- CLASE DRIVER DISPLAY 7-SEGMENTOS (5461AS-1 / 74HC595) ---
class Display7Segment:
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
        self.ds = Pin(ds, Pin.OUT)
        self.sh_cp = Pin(sh_cp, Pin.OUT)
        self.st_cp = Pin(st_cp, Pin.OUT)
        self.digitos = [
            Pin(dig1, Pin.OUT),
            Pin(dig2, Pin.OUT),
            Pin(dig3, Pin.OUT),
            Pin(dig4, Pin.OUT)
        ]
        self.apagar_digitos()
        self.buffer = [0, 0, 0, 0]
        self.activo = 0
        self.timer = Timer(0)
        
    def apagar_digitos(self):
        for d in self.digitos:
            d.value(1)
            
    def enviar_byte(self, data):
        self.st_cp.off()
        for i in range(8):
            bit = (data >> (7 - i)) & 1
            self.ds.value(bit)
            self.sh_cp.on()
            self.sh_cp.off()
        self.st_cp.on()
        
    def refrescar(self, timer_obj):
        """Callback del Timer: Multiplexa un dígito en cada llamada sin bloquear"""
        self.apagar_digitos()
        self.enviar_byte(self.buffer[self.activo])
        self.digitos[self.activo].value(0)
        self.activo = (self.activo + 1) % 4
        
    def iniciar(self):
        """Inicia el temporizador de multiplexación a intervalos de 5ms (~50Hz por dígito)"""
        self.timer.init(period=5, mode=Timer.PERIODIC, callback=self.refrescar)
        
    def detener(self):
        self.timer.deinit()
        self.apagar_digitos()
        
    def mostrar_tiempo(self, remaining_s, parpadear_punto=True):
        """Muestra los minutos y segundos en formato MM:SS"""
        mins = remaining_s // 60
        secs = remaining_s % 60
        
        d1 = mins // 10
        d2 = mins % 10
        d3 = secs // 10
        d4 = secs % 10
        
        self.buffer[0] = self.NUMEROS[d1]
        
        # Parpadeo del punto decimal del segundo dígito (minutos)
        dp_on = parpadear_punto and (remaining_s % 2 == 0)
        self.buffer[1] = self.NUMEROS[d2] | (0x80 if dp_on else 0)
        
        self.buffer[2] = self.NUMEROS[d3]
        self.buffer[3] = self.NUMEROS[d4]
        
    def mostrar_pomodoro(self, remaining_s, ciclos_focus, ocultar_vueltas=False):
        """
        Formatea el display según el diseño solicitado:
        - Dígito 1: Vueltas restantes para descanso largo (si está habilitado y no se oculta, si no, vacío).
        - Dígito 2: Vacío.
        - Dígitos 3 y 4: Minutos restantes (o segundos si queda menos de un minuto).
        """
        # 1 y 2. Vueltas restantes para descanso largo (1 o 2 dígitos)
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
                self.buffer[1] = 0b00000000 # Apagado / Vacío
            else:
                self.buffer[0] = 0b01000000 # Mostrar un guión '-' en caso inesperado
                self.buffer[1] = 0b00000000
        else:
            self.buffer[0] = 0b00000000 # Apagado / Vacío
            self.buffer[1] = 0b00000000 # Apagado / Vacío
        
        # 3. Dígitos 3 y 4: Minutos (o segundos si es < 60s)
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
        """Apaga por completo todos los dígitos del display"""
        self.buffer = [0, 0, 0, 0]
        
    def mostrar_texto(self, texto):
        """Muestra palabras básicas de hasta 4 caracteres en el display"""
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

# --- INICIALIZACIÓN DEL DISPLAY ---
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

# --- VARIABLES DE ESTADO PARA GESTOS (BOTÓN 2) ---
_last_state = 1
_press_time = 0
_release_time = 0
_click_count = 0
_long_press_triggered = False

# --- FUNCIONES DE CONTROL DE HARDWARE ---
def leer_factor_brillo_ldr():
    """
    Lee el nivel de luz ambiental desde la LDR y retorna un factor de brillo
    entre config.LDR_MIN_FACTOR y config.LDR_MAX_FACTOR.
    """
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



