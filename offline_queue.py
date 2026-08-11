# ==============================================================================
# GESTOR DE COLA OFFLINE Y SINCRONIZACIÓN DE TIEMPO REAL
# ==============================================================================
# Este módulo provee resiliencia a la telemetría del Pomodoro cuando el chip
# pierde conexión con el servidor Flask o no tiene acceso a internet:
# 1. Almacenamiento Persistente en Flash (event_queue.json) en formato FIFO.
# 2. Control de Concurrencia mediante bloqueo de hilos de MicroPython.
# 3. Formateo de marcas de tiempo relativas o absolutas mediante el RTC.
# 4. Inyección dinámica del offset de tiempo para corregir la hora en el server.

import config
import _thread
import gc

try:
    import urequests
except ImportError:
    urequests = None

try:
    import ujson as json
except ImportError:
    import json

# Lock global para evitar accesos concurrentes a la flash y llamadas de red
lock = _thread.allocate_lock()
QUEUE_FILE = "event_queue.json"
MAX_QUEUE_SIZE = 100

# Estado global de sincronización horaria del RTC
rtc_sincronizado = False

def obtener_timestamp():
    """
    Retorna la fecha y hora actual del RTC local del ESP32
    en formato legible para SQLite: YYYY-MM-DD HH:MM:SS.
    """
    try:
        import time
        # localtime retorna: (año, mes, día, hora, minuto, segundo, día_semana, día_año)
        t = time.localtime()
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])
    except Exception as e:
        print("[QUEUE WARNING] No se pudo obtener la hora del RTC:", e)
        return "2000-01-01 00:00:00"

def cargar_cola():
    """Lee el archivo event_queue.json de la flash y devuelve la lista de eventos."""
    try:
        import os
        try:
            os.stat(QUEUE_FILE)
        except OSError:
            return []
            
        with open(QUEUE_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except Exception as e:
        print("[QUEUE WARNING] Error al cargar la cola de la flash:", e)
        return []

def guardar_cola(cola):
    """Escribe la cola en el archivo event_queue.json de la flash limitando el tamaño."""
    try:
        # Mantener solo los últimos MAX_QUEUE_SIZE elementos si excede el límite
        if len(cola) > MAX_QUEUE_SIZE:
            cola = cola[-MAX_QUEUE_SIZE:]
            print("[QUEUE INFO] Límite excedido. Se descartaron eventos antiguos.")
            
        with open(QUEUE_FILE, "w") as f:
            json.dump(cola, f)
            
        # Sincronizar sistema de archivos si la plataforma lo requiere
        try:
            import os
            os.sync()
        except:
            pass
    except Exception as e:
        print("[QUEUE ERROR] No se pudo guardar la cola en la flash:", e)

def _enviar_post(url, payload):
    """
    Realiza una solicitud HTTP POST síncrona con el payload provisto.
    Si payload['sync'] es False, inyecta la hora actual del RTC de envío.
    Retorna True si el servidor responde con éxito (2xx), False si falla.
    """
    if urequests is None:
        print("[QUEUE WARNING] Módulo urequests no disponible. Abortando envío.")
        return False
        
    # Inyectar dinámicamente la hora actual si no estaba sincronizado al crearse
    if payload.get("sync") is False:
        payload["current_esp_time"] = obtener_timestamp()
        
    res = None
    try:
        print("[QUEUE HTTP] Enviando POST a:", url)
        # Timeout corto de 3s para evitar congelar el hilo de fondo
        res = urequests.post(url, json=payload, timeout=3)
        status = res.status_code
        res.close()
        
        if 200 <= status < 300:
            return True
        else:
            print("[QUEUE HTTP WARNING] Servidor respondió con código de error:", status)
            return False
    except Exception as e:
        print("[QUEUE HTTP WARNING] Error de red / conexión:", e)
        if res is not None:
            try:
                res.close()
            except:
                pass
        return False

def enviar_post_con_cola(url, payload):
    """
    Envía un POST HTTP garantizando el orden (FIFO) mediante reintentos.
    - Agrega los campos 'timestamp' y 'sync' si no están presentes.
    - Si hay elementos en la cola, intenta enviar el primero.
    - Si falla, detiene el envío y encola el evento reciente para preservar el orden.
    - Si tiene éxito, limpia la cola y envía el nuevo evento.
    Retorna True si todos los envíos tuvieron éxito (cola vacía), False si algo falló.
    """
    global lock, rtc_sincronizado
    
    # Asegurar que el payload tenga información de tiempo del momento en que ocurrió
    if "timestamp" not in payload:
        payload["timestamp"] = obtener_timestamp()
    if "sync" not in payload:
        payload["sync"] = rtc_sincronizado
        
    with lock:
        cola = cargar_cola()
        
        # Caso 1: Cola vacía. Intentar envío directo
        if not cola:
            exito = _enviar_post(url, payload)
            if exito:
                return True
            else:
                print("[QUEUE] Envío directo fallido. Guardando evento en cola...")
                cola.append({"url": url, "payload": payload})
                guardar_cola(cola)
                return False
                
        # Caso 2: La cola tiene elementos. Intentar vaciarla en orden FIFO.
        print("[QUEUE] Procesando cola offline. Elementos pendientes:", len(cola))
        
        # Intentar enviar el primero
        primer_item = cola[0]
        exito_primero = _enviar_post(primer_item["url"], primer_item["payload"])
        
        if not exito_primero:
            print("[QUEUE] Servidor sigue offline. Encolando evento nuevo al final de la fila...")
            cola.append({"url": url, "payload": payload})
            guardar_cola(cola)
            return False
            
        # El primero se envió con éxito. Lo removemos.
        cola.pop(0)
        guardar_cola(cola)
        
        # Continuar procesando los demás elementos de la cola
        while len(cola) > 0:
            siguiente_item = cola[0]
            exito_siguiente = _enviar_post(siguiente_item["url"], siguiente_item["payload"])
            if not exito_siguiente:
                print("[QUEUE] Conexión interrumpida durante el vaciado. Encolando evento nuevo...")
                cola.append({"url": url, "payload": payload})
                guardar_cola(cola)
                return False
            cola.pop(0)
            guardar_cola(cola)
            
        # Cola vaciada con éxito. Ahora enviar el evento nuevo.
        exito_nuevo = _enviar_post(url, payload)
        if exito_nuevo:
            print("[QUEUE SUCCESS] Cola completamente procesada y evento nuevo enviado.")
            return True
        else:
            print("[QUEUE WARNING] Evento nuevo falló tras vaciar la cola. Encolando...")
            cola.append({"url": url, "payload": payload})
            guardar_cola(cola)
            return False
