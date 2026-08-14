import time
import machine
import config

print("\n--- POMODORO ESP32 v{} ---".format(config.VERSION))

# ==============================================================================
# SECUENCIA DE ARRANQUE Y OPTIMIZACIÓN DE MEMORIA RAM
# ==============================================================================
# Liberamos la memoria no utilizada (gc.collect()) como buena práctica en el
# arranque del chip para tener la mayor cantidad de heap disponible.
import gc
gc.collect()

# ==============================================================================
# DETECCIÓN DE CAUSA DE REINICIO (GESTIÓN DE DEEP SLEEP)
# ==============================================================================
# La ESP32 entra en Deep Sleep por inactividad para ahorrar energía. Al presionar
# el botón único, el chip despierta provocando un reset.
# - Si es un despertar de Deep Sleep: Simplemente emitimos un tono de despertar
#   e iniciamos en modo STANDBY (espera pasiva) por defecto.
reset_causa = machine.reset_cause()
if reset_causa == machine.DEEPSLEEP_RESET:
    print("\n[RESET] Despertado por botón. Iniciando en modo STANDBY.")
    import audio
    audio.play_sleep_out()
else:
    print("\n[RESET] Inicio en frío detectado.")

# ==============================================================================
# INICIALIZACIÓN DE SERVICIOS DE RED (HTTP & SYNC)
# ==============================================================================
# Para evitar errores de memoria (MBEDTLS_ERR_X509_ALLOC_FAILED) durante el apretón
# de manos SSL (HTTPS) con GitHub, no debemos cargar módulos pesados como 'server' o
# 'pomodoro' antes de la comprobación OTA. Realizamos una conexión Wi-Fi ligera primero.

def conectar_wifi_ligero():
    import network
    import time
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return wlan.ifconfig()[0]
        
    wlan.active(True)
    if not config.WIFI_SSID:
        return "Offline"
        
    print("Conectando a WiFi (modo ligero) '{}'...".format(config.WIFI_SSID))
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    
    timeout = 10
    start = time.time()
    while not wlan.isconnected() and (time.time() - start) < timeout:
        time.sleep_ms(500)
        print(".", end="")
    print("")
    
    if wlan.isconnected():
        return wlan.ifconfig()[0]
    return "Offline"

# Intentar conexión ligera y correr OTA
ip = conectar_wifi_ligero()
if ip != "Offline":
    try:
        import ota
        ota.check_and_perform_ota()
    except Exception as e:
        print("[OTA ERROR] Fallo en chequeo OTA:", e)
        
    # Sincronizar configuración con el servidor Vercel (mientras la RAM está limpia)
    try:
        config.sincronizar_config()
    except Exception as e:
        print("[SYNC ERROR] Fallo en sincronización de configuración:", e)

# ------------------------------------------------------------------------------
# Carga de módulos pesados tras liberar/comprobar actualizaciones y sincronizar
# ------------------------------------------------------------------------------
import pomodoro
import audio

# Si la conexión ligera falló, el ESP32 continuará en modo local (Offline)
if ip == "Offline":
    print("\n[WIFI] No se pudo conectar a la red Wi-Fi. Funcionando en modo OFFLINE local.")
else:
    print("\n[WIFI SUCCESS] Dirección IP de la ESP32: http://{}".format(ip))

print("--> Sistema Pomodoro ESP32 Listo. Esperando interacción por botón.\n")

# ==============================================================================
# BUCLE PRINCIPAL NO BLOQUEANTE (STATE POLLING)
# ==============================================================================
# Para mantener la pantalla multiplexada refrescándose constantemente sin parpadeos
# y que la placa no se congele, el bucle principal no debe contener funciones
# bloqueantes (como 'time.sleep' prolongados o sockets síncronos sin timeout).
#
# En cada iteración:
# 1. Se actualizan los temporizadores y la máquina de estados del Pomodoro.
# 2. Se evalúa el temporizador de inactividad para entrar en Deep Sleep.
# 3. Se duerme 10ms (LOOP_SLEEP_MS) para liberar tiempo de CPU y reducir consumo.
while True:

    # Ejecutar tick de la máquina de estados del Pomodoro
    pomodoro.ejecutar_pomodoro_step()

    # Evaluar si debe entrar en Deep Sleep por inactividad
    pomodoro.verificar_y_ejecutar_sleep()

    # Pausa ligera de ciclo
    time.sleep_ms(config.LOOP_SLEEP_MS)
