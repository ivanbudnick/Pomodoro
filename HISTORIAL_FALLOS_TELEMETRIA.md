# Historial de Fallos y Soluciones de Telemetría (ESP32 - MicroPython)

Este archivo centraliza el historial de problemas encontrados durante el desarrollo de la telemetría remota (conexión con 3D-Moai en Vercel/Supabase) y las soluciones aplicadas. Su propósito es servir como **base de conocimiento** para evitar la regresión de errores en futuras modificaciones.

---

## Índice de Errores y Lecciones Aprendidas

### 1. El Hilo Secundario se Cuelga al Envolver el Socket en SSL (`ssl.wrap_socket`)
* **Síntoma**: Los logs mostraban que el hilo de telemetría se iniciaba, pero al intentar realizar la llamada `POST` a `/api/pomodoro/stats`, se congelaba indefinidamente en el paso `Envolviendo socket en SSL...`.
* **Causa**: MicroPython en ESP32 requiere un tamaño considerable de memoria de pila (C-stack) para realizar el handshake de cifrado SSL/TLS de mbedTLS. El hilo de telemetría fue iniciado con un stack limitado de `8192` bytes (8KB). Al llamar a `ssl.wrap_socket`, la pila se desbordaba (Stack Overflow) de forma silenciosa, corrompiendo la memoria y bloqueando el hilo de ejecución.
* **Solución**: Se incrementó el tamaño de pila del hilo a **`20480` bytes (20KB)** en `config.py` antes de invocar `_thread.start_new_thread`. Esto garantiza suficiente margen de maniobra para el handshake HTTPS.
* **Lección**: Las operaciones HTTPS/SSL en hilos secundarios de MicroPython **siempre** requieren una pila de al menos 16KB-20KB.

### 2. Las Filas no se Escriben en Supabase (Cierre Incompleto de Conexiones TCP)
* **Síntoma**: La consola de la ESP32 indicaba envío exitoso en local, pero las filas de estadísticas no aparecían en el dashboard web ni en Supabase.
* **Causa**: Para peticiones `POST`, el cliente optimizado (`_http_request_optimizado`) sólo leía la primera línea de respuesta (`Status Code`) e inmediatamente cerraba el socket para liberar buffers. Al no leer el resto del cuerpo y las cabeceras devueltas por Vercel, el socket del lado del cliente se cerraba mientras aún había datos por leer en el buffer. Esto obligaba a la pila de red de la ESP32 a enviar un paquete TCP `RST` (Reset) en vez de `FIN`. El proxy de Vercel/Cloudflare interpretaba el `RST` como un error de aborto de conexión, terminando la ejecución de la función lambda del backend antes de que el controlador de Next.js finalizara los inserts en la base de datos de Supabase.
* **Solución**: Se modificó `_http_request_optimizado` para que **siempre** consuma y descarte por completo la respuesta (cabeceras y cuerpo) en GET y POST antes de invocar `s.close()`. Esto garantiza una desconexión TCP limpia (`FIN` handshake).
* **Lección**: No se debe cerrar prematuramente un socket HTTP si el servidor sigue enviando cabeceras o cuerpo, ya que un `RST` invalida las transacciones del backend serverless.

### 3. Agotamiento Crítico de Memoria Heap (`ENOMEM` / `MBEDTLS_ERR_X509_ALLOC_FAILED`)
* **Síntoma**: Excepciones de alocación de certificados y memoria insuficiente después de completar 2 o 3 ciclos de Pomodoro.
* **Causa**: Por cada cambio de estado (iniciar focus, completar focus, iniciar descanso, etc.), la placa encolaba de forma simultánea múltiples peticiones HTTPS seguidas. Al ser HTTPS extremadamente demandante en MicroPython (cada wrap SSL consume entre 15KB y 20KB de Heap dinámico), la cola asíncrona creaba y destruía sockets SSL demasiado rápido, superando la velocidad de recolección de basura y fragmentando el Heap hasta agotar la RAM libre.
* **Solución**: 
  - Se eliminó la función redundante `reportar_ciclo` y sus llamadas correspondientes (`INICIADO` / `COMPLETADO`). Ahora la telemetría solo se envía **una vez** al finalizar el ciclo, pausar o reaccionar.
  - Se agregaron llamadas explícitas a `gc.collect()` justo antes de envolver el socket en SSL para garantizar el mayor bloque continuo de RAM disponible al momento de iniciar la conexión HTTPS.
* **Lección**: Las llamadas SSL sucesivas en MicroPython deben ser limitadas y espaciadas. Es vital ejecutar `gc.collect()` antes de operaciones pesadas como `ssl.wrap_socket()`.

### 4. Bloqueo Permanente de Conexión (Falta de Timeout SSL)
* **Síntoma**: Sockets colgados indefinidamente al haber cortes de internet o latencia en el servidor.
* **Causa**: El timeout establecido en el socket crudo (`s.settimeout(5)`) se pierde tras la envoltura de `ssl.wrap_socket(s)`. Si la red fallaba a la mitad de la transmisión de datos, el cliente SSL quedaba atrapado en una lectura infinita.
* **Solución**: Se re-aplica el timeout de 5 segundos directamente sobre el objeto socket envuelto en SSL utilizando un bloque try-except.
* **Lección**: Re-aplicar timeouts tras envolver sockets en SSL en MicroPython.

### 5. Crash Fatal por NameError (`enviar_reporte_flask`)
* **Síntoma**: La placa se colgaba de manera irreversible al hacer avance forzado (doble clic) en medio de un ciclo.
* **Causa**: Intentaba invocar a `enviar_reporte_flask`, una función que fue renombrada/eliminada en la transición a Next.js (3D-Moai).
* **Solución**: Se reemplazó por la función correcta de telemetría de nube: `enviar_reporte_nube(..., forzado=1)`.

### 6. Agotamiento de Memoria del Sistema (System Heap ENOMEM) por Pila de Hilo Secundario
* **Síntoma**: La envoltura del socket en SSL (`ssl.wrap_socket`) fallaba con `[Errno 12] ENOMEM` a pesar de que el heap de MicroPython mostraba más de 84KB de RAM libre (`gc.mem_free()`).
* **Causa**: mbedTLS (código C de ESP-IDF) realiza alocaciones dinámicas para el handshake HTTPS en el heap del sistema (ESP-IDF heap, fuera de MicroPython). Un hilo secundario requiere que ESP-IDF asigne su pila (stack) de 20KB directamente desde este mismo heap del sistema. Al estar el hilo activo, consumía de forma permanente 20KB de RAM del sistema, dejando al mbedTLS sin suficiente memoria contigua para los buffers de cifrado (30KB+), lo que resultaba en fallas de `ENOMEM`.
* **Solución**: Se eliminó por completo el hilo secundario y la cola asíncrona. La telemetría ahora se procesa de forma **síncrona** en el hilo principal. Para que este bloqueo de 1.5 a 2 segundos se vea profesional, se diseñó una **animación artística de sincronización** (el LED RGB se ilumina de color Cian suave `R=0, G=200, B=400` mediante PWM por hardware, el cual continúa oscilando en background aunque la CPU esté bloqueada).
* **Lección**: Las peticiones HTTPS/SSL en ESP32 son extremadamente demandantes en el heap del sistema (mbedTLS). Evitar el overhead de hilos secundarios y ejecutar la red de forma síncrona en puntos de transición de estados.

### 7. Agotamiento de Heap del Sistema por Sockets en `TIME_WAIT` (Error `MBEDTLS_ERR_X509_ALLOC_FAILED`)
* **Síntoma**: La primera petición HTTPS (OTA o sincronización al arrancar) funcionaba correctamente, pero la siguiente petición HTTPS realizada a los pocos segundos (sincronización al presionar comenzar, o envío de telemetría inicial) fallaba con `MBEDTLS_ERR_X509_ALLOC_FAILED`.
* **Causa**: El protocolo TCP mantiene los sockets cerrados en estado `TIME_WAIT` durante 120 segundos para evitar paquetes perdidos de conexiones anteriores. En ESP32, mantener múltiples conexiones SSL en `TIME_WAIT` consume recursos del stack de red (LwIP) en el heap del sistema. Si se realizan múltiples llamadas HTTPS consecutivas en menos de 2 minutos (como OTA, config boot, config start, e inicio de ciclo), el heap del sistema se agota y mbedTLS no puede alocar memoria para procesar el certificado del servidor.
* **Solución**:
  - Se configuró la opción de socket `SO_LINGER` a `0` en `_http_request_optimizado` antes de realizar la conexión. Esto fuerza al socket a cerrarse enviando un paquete `RST` en lugar de un handshake de desconexión `FIN`, liberando la conexión del stack de LwIP de forma instantánea sin entrar en `TIME_WAIT`.
  - Se implementó un throttling de sincronización en `sincronizar_config()`, guardando una marca de tiempo (`last_sync_time`). Si el dispositivo ya sincronizó sus tiempos hace menos de 60 segundos (por ejemplo, al arrancar la placa), se omite el GET de configuración redundante al presionar "Comenzar", reduciendo el tráfico y consumo de sockets SSL.
* **Lección**: En microcontroladores, los sockets SSL deben cerrarse mediante `SO_LINGER=0` (RST) una vez finalizada la transferencia, y se debe evitar realizar llamadas GET/POST repetitivas o consecutivas en intervalos cortos.

---

## Resumen de Reglas para Futuras Modificaciones

1. **Evitar Hilos Secundarios para SSL**: No procesar solicitudes HTTPS/SSL en hilos secundarios. Realizarlas de forma síncrona en el hilo principal durante las transiciones de estados (pausa, fin de ciclo, reacción) aprovechando el hardware PWM para mantener una animación de sincronización visual (LED Cian suave).
2. **Evitar estado TIME_WAIT**: Utilizar la opción `SO_LINGER = 0` (l_onoff=1, l_linger=0) en todos los sockets antes de conectarse para asegurar que la memoria de red de LwIP y los descriptores se liberen inmediatamente tras el cierre.
3. **Throttling de Conexiones**: No realizar solicitudes HTTP repetitivas. Comprobar que transcurra al menos 60 segundos entre pings o sincronizaciones de parámetros utilizando marcas de tiempo locales.
4. **Cerrar Sockets Limpiamente**: Asegurar siempre que se leen todos los datos de respuesta antes de cerrar el socket (bucle de lectura hasta el EOF) para no interrumpir los procesos en servidores serverless.
5. **Control de Memoria**: Usar `gc.collect()` proactivamente antes de llamadas de red SSL.
6. **Verificación de Encolado**: Evitar duplicar reportes para el mismo evento físico. Utilizar `enviar_reporte_nube` y evitar reintroducir `reportar_ciclo`.


