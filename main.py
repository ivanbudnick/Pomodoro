import time
import machine
import config
import pomodoro
import audio

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
# el botón físico de inicio (GPIO 25), el chip despierta provocando un reset.
# Aquí evaluamos si el reinicio es debido a haber despertado de Deep Sleep.
#
# - Si es un despertar de Deep Sleep: Inicializamos la máquina de estados
#   directamente en modo FOCUS, emitiendo un tono agradable de encendido
#   y comenzando a contar la sesión de inmediato para mejorar la respuesta al usuario.
# - Si es un encendido en frío (por ejemplo, al conectar el cable USB): Simplemente
#   imprimimos el log e iniciamos en modo STANDBY (espera pasiva).
reset_causa = machine.reset_cause()
if reset_causa == machine.DEEPSLEEP_RESET:
    print("\n[RESET] Despertado por botón. Iniciando directamente en modo FOCUS.")
    pomodoro.estado_actual = pomodoro.ESTADO_FOCUS
    pomodoro.pausado = False
    pomodoro.cronometro = time.ticks_ms()
    pomodoro.tiempo_acumulado_ms = 0
    # Emitir pitido de inicio ascendente de despertar
    audio.play_sleep_out()
else:
    print("\n[RESET] Inicio en frío detectado.")

# ==============================================================================
# INICIALIZACIÓN DE SERVICIOS DE RED (HTTP & SYNC)
# ==============================================================================
# Cargamos el módulo de servidor HTTP. Conectamos a la red Wi-Fi utilizando
# las credenciales cargadas. Si el dispositivo está en línea, sincronizamos la
# configuración de los tiempos (Focus, Descansos, etc.) desde la base de datos
# centralizada del servidor de la PC.
import server

ip = server.connect_wifi()
if ip != "Offline":
    server.sincronizar_config_pc()

# Iniciar el socket del servidor HTTP para recibir y responder solicitudes del Dashboard
server.iniciar_servidor_http()

print("--> Sistema Pomodoro ESP32 Listo. Esperando interacción por botón o web.\n")

# ==============================================================================
# BUCLE PRINCIPAL NO BLOQUEANTE (STATE POLLING)
# ==============================================================================
# Para mantener la pantalla multiplexada refrescándose constantemente sin parpadeos
# y que la placa no se congele, el bucle principal no debe contener funciones
# bloqueantes (como 'time.sleep' prolongados o sockets síncronos sin timeout).
#
# En cada iteración:
# 1. Se atienden peticiones HTTP entrantes (no bloqueante, timeout muy corto).
# 2. Se actualizan los temporizadores y la máquina de estados del Pomodoro.
# 3. Se evalúa el temporizador de inactividad para entrar en Deep Sleep.
# 4. Se duerme 10ms (LOOP_SLEEP_MS) para liberar tiempo de CPU y reducir consumo.
while True:
    # Atender solicitudes HTTP entrantes
    server.atender_peticiones_http()

    # Ejecutar tick de la máquina de estados del Pomodoro
    pomodoro.ejecutar_pomodoro_step()

    # Evaluar si debe entrar en Deep Sleep por inactividad
    pomodoro.verificar_y_ejecutar_sleep()

    # Pausa ligera de ciclo
    time.sleep_ms(config.LOOP_SLEEP_MS)
