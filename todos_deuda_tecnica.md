# TODOs y Deudas Técnicas Pendientes

Este documento centraliza los puntos de mejora identificados, deudas técnicas acumuladas y limitaciones actuales del sistema Pomodoro IoT para su resolución en futuras iteraciones.

---

## 1. Conectividad y Sincronización Remota (Fuera de LAN)

### Limitación Actual
* El mecanismo de autodescubrimiento UDP broadcast y las conexiones HTTP directas a IPs privadas (`192.168.x.x`) están restringidos al ámbito de la red local (LAN). Si la ESP32 se traslada a otra ubicación física (distinta red WiFi) y el servidor Flask permanece en la PC de origen, no habrá sincronización ni reportería.

### TODOs / Soluciones Propuestas
- [ ] **Soporte para Backend en la Nube / Broker Público**: Configurar un broker MQTT público (como HiveMQ con credenciales) o una URL pública de backend como fallback secundario persistente.
- [ ] **Configuración de IP Remota en Portal Cautivo**: Modificar el formulario web del Portal Cautivo (WiFi Manager) para permitir al usuario ingresar una URL del servidor PC de forma manual (útil para ingresar URLs de túneles como Localtunnel, Ngrok o dominios públicos).

---

## 2. Seguridad en Exposición Pública

### Limitación Actual
* El servidor de PC en `backend/app.py` corre en modo debug (`debug=True`) y no implementa ninguna capa de autenticación ni validación de origen en sus endpoints REST/HTTP.
* Si el usuario expone el servidor Flask a Internet usando túneles (Localtunnel/Ngrok) para conectar la ESP32 remotamente, cualquier persona que descubra la URL pública generada podrá acceder al Dashboard y modificar la base de datos o configuraciones.

### TODOs / Soluciones Propuestas
- [ ] **Autenticación mediante Clave API (API Key)**: Implementar una validación sencilla basada en tokens/headers (ej. header `X-API-Key`) en el firmware de la ESP32 y el backend Flask para asegurar que solo la placa autorizada envíe datos o descargue configuraciones.
- [ ] **Desactivar Debug Mode en Producción**: Modificar el script de arranque para correr Flask en un servidor WSGI de producción (como `gunicorn` o `waitress`) y desactivar el modo debug cuando se exponga a la red externa.

---

## 3. Resiliencia de Telemetría Offline

### Limitación Actual
* Si la ESP32 pierde la conexión WiFi o el servidor PC se apaga durante un ciclo Focus, los reportes se descartan silenciosamente (el hilo de fondo asíncrono imprime un warning en consola y finaliza la petición). No hay reintentos ni almacenamiento local.

### TODOs / Soluciones Propuestas
- [ ] **Cola de Métricas en Flash (Buffer Local)**: Implementar una cola local simple (FIFO) que guarde temporalmente los ciclos finalizados en un archivo JSON en la Flash de la ESP32 si falla el envío. Al recuperar conexión con el servidor, realizar un envío masivo de la cola acumulada (batching).

---

## 4. Estabilidad del Autodescubrimiento UDP

### Limitación Actual
* En redes con **AP Isolation** activado (común en redes de oficina, universidades o WiFi público de hoteles), los dispositivos conectados a la misma red no pueden comunicarse entre sí, bloqueando el descubrimiento UDP y la conexión directa.

### TODOs / Soluciones Propuestas
- [ ] **Manejo Explicito de Excepciones de AP Isolation**: Documentar la limitación en el manual de usuario.
- [ ] **Búsqueda por Subred (Ping Secuencial)**: Como última instancia alternativa antes de usar el fallback, implementar un escaneo rápido en segundo plano (ping secuencial en la subred `/24` al puerto `5001`) si el broadcast UDP no responde.
