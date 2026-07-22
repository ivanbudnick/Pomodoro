import time
import machine
import config
import pomodoro
import server
import audio

# 1. Verificar causa del reinicio para comportamiento inteligente tras Deep Sleep
reset_causa = machine.reset_cause()
if reset_causa == machine.DEEPSLEEP_RESET:
    print("\n[RESET] Despertado por botón. Iniciando directamente en modo FOCUS.")
    pomodoro.estado_actual = pomodoro.ESTADO_FOCUS
    pomodoro.pausado = False
    pomodoro.cronometro = time.ticks_ms()
    pomodoro.tiempo_acumulado_ms = 0
    # Emitir pitido de inicio
    audio.play_sleep_out()
else:
    print("\n[RESET] Inicio en frío detectado.")

# 2. Conectar a la red WiFi (si está configurada)
ip = server.connect_wifi()
if ip != "Offline":
    server.sincronizar_config_pc()

# 3. Iniciar Servidor HTTP embebido en puerto 80
server.iniciar_servidor_http()

print("--> Sistema Pomodoro ESP32 Listo. Esperando interacción por botón o web.\n")

# 4. Bucle Principal No Bloqueante
while True:
    # Atender solicitudes HTTP entrantes
    server.atender_peticiones_http()

    # Ejecutar tick de la máquina de estados del Pomodoro
    pomodoro.ejecutar_pomodoro_step()

    # Evaluar si debe entrar en Deep Sleep por inactividad
    pomodoro.verificar_y_ejecutar_sleep()

    # Pausa ligera de ciclo
    time.sleep_ms(config.LOOP_SLEEP_MS)
