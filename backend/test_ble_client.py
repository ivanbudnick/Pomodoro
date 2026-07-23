import asyncio
import sys
from bleak import BleakScanner, BleakClient

# UUIDs de Nordic UART Service (NUS) coincidiendo con ble_uart.py
UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e" # Para enviarle comandos a la ESP32
UART_TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e" # Para recibir notificaciones del estado

# Mapeo de IDs de estados a nombres para visualización
ESTADOS_NOMBRADOS = {
    0: "STANDBY (Amarillo)",
    1: "FOCUS (Rojo)",
    2: "DESCANSO CORTO (Azul)",
    3: "DESCANSO LARGO (Verde)",
    4: "ALERTA (Titilando)"
}

def notification_handler(sender, data):
    """Callback que procesa los mensajes del ESP32 cuando el tiempo o estado cambia"""
    try:
        decoded = data.decode('utf-8').strip()
        if decoded.startswith("S:"):
            # Formato: S:<estado_id>,<pausado_0_1>,<remaining_s>,<ciclos_completados>
            parts = decoded[2:].split(",")
            if len(parts) == 4:
                estado_id = int(parts[0])
                pausado = int(parts[1]) == 1
                remaining_s = int(parts[2])
                ciclos = int(parts[3])
                
                # Formatear el tiempo en MM:SS
                minutos = remaining_s // 60
                segundos = remaining_s % 60
                tiempo_str = f"{minutos:02d}:{segundos:02d}"
                
                estado_str = ESTADOS_NOMBRADOS.get(estado_id, f"DESCONOCIDO ({estado_id})")
                modo_pausa = " [PAUSADO]" if pausado else ""
                
                # Imprimir en la misma línea usando retorno de carro y limpiando la línea
                sys.stdout.write("\r\033[K") # Limpiar línea en terminales compatibles
                sys.stdout.write(f"\r[ESP32 STATUS] Estado: {estado_str}{modo_pausa} | Tiempo: {tiempo_str} | Ciclos Focus: {ciclos} | (Teclas: [Enter] Pausa, [r] Reiniciar, [s] Standby, [g] Iniciar, [q] Salir)")
                sys.stdout.flush()
    except Exception as e:
        print(f"\n[CLIENT ERROR] Error al procesar notificación: {e}")

async def listen_to_keyboard(client):
    """Escucha la entrada del teclado en la terminal y envía comandos por BLE"""
    loop = asyncio.get_event_loop()
    print("\n[CLIENT INFO] Escribí comandos y presioná Enter:")
    print(" - Presioná Enter (vacío) para Pausar/Reanudar (PLAY/PAUSE)")
    print(" - 'g' + Enter para Iniciar Focus (START)")
    print(" - 'r' + Enter para Reiniciar la fase actual (RESET)")
    print(" - 's' + Enter para Volver a Standby (RESET_IDLE)")
    print(" - 'q' + Enter para Salir")
    print("-" * 80)
    
    while True:
        # Leer de forma asíncrona la entrada estándar
        user_input = await loop.run_in_executor(None, sys.stdin.readline)
        cmd_raw = user_input.strip().lower()
        
        if not client.is_connected:
            print("\n[CLIENT ERROR] Conexión perdida. Saliendo...")
            break
            
        command_to_send = None
        if cmd_raw == "q":
            print("\nDesconectando...")
            break
        elif cmd_raw == "": # Enter vacío
            command_to_send = "TOGGLE"
        elif cmd_raw == "g":
            command_to_send = "START"
        elif cmd_raw == "r":
            command_to_send = "RESET"
        elif cmd_raw == "s":
            command_to_send = "STANDBY"
        else:
            print(f"\n[CLIENT INFO] Comando '{cmd_raw}' no reconocido.")
            continue
            
        if command_to_send:
            try:
                # Enviar comando al ESP32 por la característica RX
                await client.write_gatt_char(UART_RX_CHAR_UUID, command_to_send.encode('utf-8'))
            except Exception as e:
                print(f"\n[CLIENT ERROR] Error al enviar comando: {e}")

async def main():
    print("=====================================================================")
    print("          POMODORO ESP32 - CLIENTE BLUETOOTH CONTROL PANEL           ")
    print("=====================================================================")
    print("[BLE] Iniciando escaneo de 5 segundos...")
    
    # 1. Escanear y listar dispositivos para dar feedback visual
    devices = await BleakScanner.discover(timeout=5.0)
    device = None
    
    print("\n--- Dispositivos Bluetooth detectados en el área ---")
    for d in devices:
        name = d.name or "Sin nombre / Oculto"
        print(f" * Dirección: {d.address} | Nombre: {name}")
        if "Pomodoro-ESP32" in name:
            device = d
            
    # 2. Si no se encontró en el escaneo rápido, usar filtro exhaustivo de anuncio
    if not device:
        print("\n[BLE] Buscando de forma exhaustiva con filtro de anuncio (10s)...")
        try:
            device = await BleakScanner.find_device_by_filter(
                lambda d, ad: (d.name and "Pomodoro-ESP32" in d.name) or (ad.local_name and "Pomodoro-ESP32" in ad.local_name),
                timeout=10.0
            )
        except Exception as e:
            print(f"[BLE] Error durante el escaneo con filtro: {e}")
            
    if not device:
        print("\n[BLE ERROR] No se encontró el dispositivo 'Pomodoro-ESP32'.")
        print("Asegurate de que:")
        print(" 1. La ESP32 esté encendida y el monitor serial diga '[BLE] Anunciando dispositivo: Pomodoro-ESP32'.")
        print(" 2. El Bluetooth de tu Mac esté activado (probá apagarlo y volverlo a encender).")
        return
        
    print(f"\n[BLE SUCCESS] ¡Dispositivo encontrado! Dirección: {device.address}")
    name_display = device.name or "Pomodoro-ESP32"
    print(f"[BLE] Conectando a {name_display}...")
    
    async with BleakClient(device) as client:
        print("[BLE SUCCESS] ¡Conectado con éxito!")
        
        # Suscribirse a la característica TX del ESP32
        print("[BLE] Suscribiéndose a notificaciones de estado...")
        await client.start_notify(UART_TX_CHAR_UUID, notification_handler)
        
        # Correr el listener de teclado de forma interactiva
        await listen_to_keyboard(client)
        
        # Desuscribirse al salir
        await client.stop_notify(UART_TX_CHAR_UUID)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCliente terminado por el usuario.")
    except Exception as e:
        print(f"\nFallo crítico del cliente BLE: {e}")
