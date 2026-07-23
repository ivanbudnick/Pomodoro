import bluetooth
from micropython import const

# Constantes de eventos IRQ de BLE en MicroPython
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# UUIDs estándares del servicio Nordic UART (NUS)
_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_RX_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
_TX_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")

_UART_SERVICE = (
    _UART_UUID,
    (
        (_TX_UUID, bluetooth.FLAG_NOTIFY),
        (_RX_UUID, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
    ),
)

class BLEUART:
    def __init__(self, name="Pomodoro-ESP32"):
        import gc
        gc.collect() # Liberar memoria fragmentada antes de reservar recursos BLE
        
        self._ble = bluetooth.BLE()
        self._ble.active(False) # Asegurar reset de la radio ante reinicios por software
        self._ble.active(True)
        self._ble.irq(self._irq)
        
        # Registrar el servicio UART
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((_UART_SERVICE,))
        
        self._connections = set()
        self._rx_buffer = bytearray()
        self._handler = None
        self._name = name
        
        # Iniciar anuncios publicitarios
        self._advertise()

    def _advertise(self):
        # 1. Payload de Anuncio Principal (adv_data)
        # Flags estándar: Modo General Descubrible, BR/EDR No Soportado (3 bytes)
        adv_data = bytearray(b'\x02\x01\x06')
        
        # Incluir el Nombre Completo Local en el anuncio principal para visibilidad inmediata en macOS (16 bytes)
        name_bytes = self._name.encode('utf-8')
        adv_data += bytearray([len(name_bytes) + 1, 0x09]) + name_bytes
        
        # 2. Payload de Respuesta de Escaneo (resp_data)
        # Incluir el UUID del servicio de 128-bit en la respuesta de escaneo (18 bytes)
        uuid_bytes = bytes(_UART_UUID)
        resp_data = bytearray([len(uuid_bytes) + 1, 0x07]) + uuid_bytes
        
        # Publicitar cada ~100ms (interval_us = 100000)
        self._ble.gap_advertise(100000, adv_data, resp_data=resp_data)
        print("[BLE] Anunciando dispositivo: {}".format(self._name))

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
            print("[BLE] Cliente central conectado. Handle: {}".format(conn_handle))
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            if conn_handle in self._connections:
                self._connections.remove(conn_handle)
            print("[BLE] Cliente central desconectado. Handle: {}. Reiniciando anuncios...".format(conn_handle))
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._rx_handle:
                # Leer datos recibidos del cliente central
                data_read = self._ble.gatts_read(self._rx_handle)
                self._rx_buffer.extend(data_read)
                if self._handler:
                    # Notificar al callback registrado en el hilo principal
                    self._handler()

    def write(self, data):
        """Envía datos (string o bytes) a todos los clientes centrales conectados."""
        if not self.esta_conectado():
            return
        
        # Convertir a bytes si es string
        if isinstance(data, str):
            data = data.encode('utf-8')
            
        for conn_handle in self._connections:
            try:
                self._ble.gatts_notify(conn_handle, self._tx_handle, data)
            except Exception as e:
                print("[BLE WRITE ERROR] Error al notificar al handle {}: {}".format(conn_handle, e))

    def read(self):
        """Retorna todos los bytes acumulados en el buffer y lo vacía."""
        result = bytes(self._rx_buffer)
        self._rx_buffer = bytearray()
        return result

    def any(self):
        """Retorna True si hay bytes esperando a ser leídos en el buffer."""
        return len(self._rx_buffer) > 0

    def esta_conectado(self):
        """Retorna True si hay al menos un cliente conectado."""
        return len(self._connections) > 0

    def set_handler(self, handler):
        """Configura un callback que se ejecuta al recibir datos."""
        self._handler = handler
