import time
import config
import pomodoro
import server

# 1. Conectar a la red WiFi (si está configurada)
ip = server.connect_wifi()
if ip != "Offline":
    server.sincronizar_config_pc()

# 2. Iniciar Servidor HTTP embebido en puerto 80
server.iniciar_servidor_http()

print("--> Sistema Pomodoro ESP32 Listo. Esperando interacción por botón o web.\n")

# 3. Bucle Principal No Bloqueante
while True:
    # Atender solicitudes HTTP entrantes
    server.atender_peticiones_http()

    # Ejecutar tick de la máquina de estados del Pomodoro
    pomodoro.ejecutar_pomodoro_step()

    # Pausa ligera de ciclo
    time.sleep_ms(config.LOOP_SLEEP_MS)
