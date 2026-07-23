# ==============================================================================
# CONTROLADOR BLUETOOTH BLE - SERVICIO NORDIC UART (NUS)
# ==============================================================================
# Este módulo implementa la conectividad Bluetooth Low Energy (BLE) utilizando
# la API de bajo nivel de MicroPython. Se expone como un puerto serie inalámbrico
# compatible con el perfil estándar "Nordic UART Service" (NUS).
#
# Arquitectura del Perfil NUS:
# - UUID del Servicio UART: 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
# - Característica RX (Escritura): Recibe comandos del cliente central (PC/Móvil).
# - Característica TX (Notificación): Envía actualizaciones del estado del Pomodoro.
#
# Manejo del Buffer de Recepción (RX):
# Las solicitudes entrantes se acumulan en un buffer circular (bytearray) que el
# hilo principal consume periódicamente de forma asíncrona mediante llamadas a 'read()'.

import bluetooth
from micropython import const

# --- CONSTANTES DE EVENTOS IRQ DE BLE ---
# Códigos numéricos de interrupciones enviados por el controlador NimBLE
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# --- DEFINICIÓN DE UUIDS ESTÁNDARES DE NORDIC UART SERVICE ---
_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_RX_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
_TX_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")

# Estructura del Servicio GATTS para registro en el microcontrolador
_UART_SERVICE = (
    _UART_UUID,
    (
        (_TX_UUID, bluetooth.FLAG_NOTIFY),  # Permitir notificaciones automáticas al cliente
        (_RX_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),  # Permite escritura rápida sin acuse
    ),
)

class BLEUART:
    def __init__(self, name="Pomodoro-ESP32"):
        import gc
        gc.collect() # Limpieza exhaustiva para garantizar un bloque continuo en memoria heap
        
        self._ble = bluetooth.BLE()
        self._ble.active(False) # Forzar apagado de la radio para reiniciar sockets previos
        self._ble.active(True)
        self._ble.irq(self._irq) # Enlazar callback de interrupciones
        
        # Registrar el servicio UART en la tabla GATT del chip
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((_UART_SERVICE,))
        
        self._connections = set()
        self._rx_buffer = bytearray()
        self._handler = None
        self._name = name
        
        # Comenzar a emitir paquetes publicitarios para ser visible por otros dispositivos
        self._advertise()

    def _advertise(self):
        """
        Construye y emite los paquetes de anuncios de GAP (Generic Access Profile).
        Debido al límite estricto de 31 bytes por paquete, dividimos la información:
        
        1. adv_data (Anuncio Principal):
           - Flags de descubrimiento general (3 bytes).
           - Nombre Local Completo del dispositivo (longitud + tag 0x09 + string UTF-8).
           
        2. resp_data (Respuesta de Escaneo):
           - UUID de 128 bits de NUS (longitud + tag 0x07 + 16 bytes UUID).
             Esto permite que apps cliente (como Bleak) filtren por servicio.
        """
        # Flags estándar: Modo General Descubrible, BR/EDR No Soportado (Solo BLE)
        adv_data = bytearray(b'\x02\x01\x06')
        
        # Incluir el Nombre Local Completo
        name_bytes = self._name.encode('utf-8')
        adv_data += bytearray([len(name_bytes) + 1, 0x09]) + name_bytes
        
        # Incluir el UUID de NUS en la respuesta de escaneo posterior
        uuid_bytes = bytes(_UART_UUID)
        resp_data = bytearray([len(uuid_bytes) + 1, 0x07]) + uuid_bytes
        
        # GAP advertise cada 100ms (interval_us = 100000)
        self._ble.gap_advertise(100000, adv_data, resp_data=resp_data)
        print("[BLE] Anunciando dispositivo: {}".format(self._name))

    def _irq(self, event, data):
        """
        Callback de Interrupción BLE ejecutado por el firmware.
        Debe procesar la información de forma extremadamente veloz para evitar
        bloquear otras rutinas de hardware de tiempo real.
        """
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
            print("[BLE] Cliente central conectado. Handle: {}".format(conn_handle))
            try:
                import hardware
                hardware.set_led_interno(True)
            except Exception as e:
                print("[BLE LED ERROR] No se pudo encender LED interno:", e)
            
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            if conn_handle in self._connections:
                self._connections.remove(conn_handle)
            print("[BLE] Cliente central desconectado. Handle: {}. Reiniciando anuncios...".format(conn_handle))
            try:
                import hardware
                hardware.set_led_interno(False)
            except Exception as e:
                print("[BLE LED ERROR] No se pudo apagar LED interno:", e)
            self._advertise()
            
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._rx_handle:
                # Leer los bytes entrantes acumulados en la característica RX
                data_read = self._ble.gatts_read(self._rx_handle)
                self._rx_buffer.extend(data_read)
                if self._handler:
                    # Invocar callback en hilo principal para procesar comandos
                    self._handler()

    def write(self, data):
        """Notifica datos en tiempo real a todos los clientes centrales conectados"""
        if not self.esta_conectado():
            return
        
        # Convertir a bytes si la entrada es un string
        if isinstance(data, str):
            data = data.encode('utf-8')
            
        for conn_handle in self._connections:
            try:
                # Envía notificaciones Push directas sin requerir handshake (rápido y eficiente)
                self._ble.gatts_notify(conn_handle, self._tx_handle, data)
            except Exception as e:
                print("[BLE WRITE ERROR] Error al notificar al handle {}: {}".format(conn_handle, e))

    def read(self):
        """Retorna todos los bytes del buffer y lo vacía (operación atómica manual)"""
        result = bytes(self._rx_buffer)
        self._rx_buffer = bytearray()
        return result

    def any(self):
        """Retorna True si hay bytes no leídos en el buffer circular"""
        return len(self._rx_buffer) > 0

    def esta_conectado(self):
        """Retorna True si hay al menos un cliente enlazado"""
        return len(self._connections) > 0

    def set_handler(self, handler):
        """Enlaza el callback que procesa los datos en el flujo del loop principal"""
        self._handler = handler

    def detener_anuncios(self):
        """Detiene temporalmente los anuncios publicitarios de GAP para liberar la radio RF."""
        try:
            self._ble.gap_advertise(None)
            print("[BLE] Anuncios detenidos temporalmente.")
        except Exception as e:
            print("[BLE ERROR] No se pudieron detener anuncios:", e)

    def iniciar_anuncios(self):
        """Reinicia los anuncios publicitarios de GAP."""
        try:
            self._advertise()
            print("[BLE] Anuncios reactivados.")
        except Exception as e:
            print("[BLE ERROR] No se pudieron reactivar anuncios:", e)
