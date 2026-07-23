from machine import Pin
import time
import config

# --- Configuración de pines para el 74HC595 ---
data_pin = Pin(config.PIN_74HC595_DS, Pin.OUT)       # DS
clock_pin = Pin(config.PIN_74HC595_SH_CP, Pin.OUT)   # SH_CP / SRCLK
latch_pin = Pin(config.PIN_74HC595_ST_CP, Pin.OUT)   # ST_CP / RCLK

# --- Configuración de pines para activar los 4 dígitos ---
# (Al ser Cátodo Común, se activan poniendo el pin en LOW / 0)
digitos = [
    Pin(config.PIN_DISPLAY_DIG1, Pin.OUT),
    Pin(config.PIN_DISPLAY_DIG2, Pin.OUT),
    Pin(config.PIN_DISPLAY_DIG3, Pin.OUT),
    Pin(config.PIN_DISPLAY_DIG4, Pin.OUT)
]

# Mapa de bits para los números 0-9 en un display de cátodo común (A-G)
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

def enviar_byte(data):
    """ Envía un byte bit a bit al 74HC595 """
    latch_pin.off()
    for i in range(8):
        # Extrae cada bit enviándolo del MSB al LSB
        bit = (data >> (7 - i)) & 1
        data_pin.value(bit)
        clock_pin.on()
        clock_pin.off()
    latch_pin.on()

def apagar_digitos():
    """ Apaga todos los dígitos poniéndolos en HIGH (1) """
    for d in digitos:
        d.value(1)

print("[TEST] Iniciando prueba de display 7-segmentos...")
print(f"Pines 74HC595: DS={config.PIN_74HC595_DS}, SH_CP={config.PIN_74HC595_SH_CP}, ST_CP={config.PIN_74HC595_ST_CP}")
print(f"Pines Dígitos: DIG1={config.PIN_DISPLAY_DIG1}, DIG2={config.PIN_DISPLAY_DIG2}, DIG3={config.PIN_DISPLAY_DIG3}, DIG4={config.PIN_DISPLAY_DIG4}")

# --- Bucle Principal ---
contador = 0

try:
    while True:
        tiempo_inicio = time.ticks_ms()
        
        # Durante 1 segundo (1000 ms) refrescamos el display rápidamente
        while time.ticks_diff(time.ticks_ms(), tiempo_inicio) < 1000:
            
            # Muestra el mismo valor en todos los dígitos secuencialmente
            for i in range(4):
                apagar_digitos()                   # 1. Evita sombras/fantasmas
                enviar_byte(NUMEROS[contador])     # 2. Envía el patrón al 74HC595
                digitos[i].value(0)                # 3. Enciende el dígito actual
                time.sleep_ms(2)                   # 4. Pequeña pausa para persistencia visual

        # Incrementa el número y reinicia al pasar de 9 (cicla de 0 a 9)
        contador = (contador + 1) % 10
except KeyboardInterrupt:
    print("[TEST] Prueba detenida por el usuario. Apagando display...")
    apagar_digitos()
