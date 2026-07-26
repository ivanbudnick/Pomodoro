# Pomodoro IoT Timer with Flask Web Dashboard

Este proyecto implementa un temporizador Pomodoro avanzado basado en MicroPython para el chip ESP32, integrado con un panel de control web Flask con estética premium "glassmorphic" en la PC y soporte de red (WiFi, HTTP, MQTT, Portal Cautivo).

---

## Especificaciones de Hardware (ESP-32S)

El firmware está optimizado para el módulo **ESP-32S (ESP-WROOM-32)**. A continuación se detalla el mapeo completo de pines físicos para los periféricos conectados:

### Periféricos de Entrada y Salida Básicos
*   **Botón 1 (Inicio/Reanudación / Despertar Deep Sleep):** `GPIO 25` (Capaz de RTC, configurado con resistencia pull-up interna).
*   **Botón 2 (Control / Pausa / Gestos):** `GPIO 22` (Configurado con resistencia pull-up interna).
*   **LED RGB (Salidas PWM con brillo regulado por LDR):**
    *   **Rojo:** `GPIO 14`
    *   **Verde:** `GPIO 27`
    *   **Blue (Azul):** `GPIO 26`
*   **Zumbador / Buzzer Pasivo (Salida PWM para tonos):** `GPIO 13`
*   **Sensor de Luz LDR (Entrada Analógica ADC):** `GPIO 34` (Canal ADC1_CH6 con atenuación de 11dB para rango 0V-3.3V).

> [!NOTE]
> Se eligió el `GPIO 25` para el botón principal de inicio/despertar para evitar interferencias de ruido analógico/RF con el cristal oscilador de 32.768 kHz que típicamente se suelda en los pines `GPIO 32` y `33` en las placas de desarrollo ESP-32S, manteniendo al mismo tiempo la capacidad de despertar del modo de ultra bajo consumo Deep Sleep.

### Display de 7 Segmentos y 4 Dígitos (Multiplexado vía 74HC595)
Para ahorrar pines de entrada/salida de la ESP32, la pantalla de cátodo común se conecta usando el registro de desplazamiento 74HC595:
*   **Datos Seriales (DS / Serial Data Input):** `GPIO 4`
*   **Reloj de Desplazamiento (SH_CP / SRCLK):** `GPIO 16`
*   **Reloj de Latch / Almacenamiento (ST_CP / RCLK):** `GPIO 17`
*   **Selector Dígito 1:** `GPIO 18`
*   **Selector Dígito 2:** `GPIO 19`
*   **Selector Dígito 3:** `GPIO 21`
*   **Selector Dígito 4:** `GPIO 23`

---

## Operación de los Estados del Sistema

El sistema implementa una máquina de estados finitos robusta en el ESP32:

1.  **Estado de Espera (STANDBY):** El LED RGB parpadea suavemente en color **Amarillo**. El display de 7 segmentos muestra `----`. El dispositivo entra en modo Deep Sleep automáticamente tras 60 segundos de inactividad para ahorrar energía. Se puede despertar presionando el **Botón 1**.
2.  **Fase de Enfoque (FOCUS):** Se activa al presionar el **Botón 1** o mediante la interfaz de red. El LED brilla en color **Rojo**, regulando su intensidad exponencialmente según transcurre la sesión. El display muestra el tiempo restante en formato `MM:SS` y la cantidad de ciclos completados.
3.  **Fase de Descanso Corto (DESCANSO_CORTO):** Se inicia automáticamente al finalizar una fase Focus. El LED brilla en color **Azul** progresivo. El display muestra el tiempo restante de descanso (ocultando los ciclos de enfoque).
4.  **Fase de Descanso Largo (DESCANSO_LARGO):** Ocurre de forma automática al completar un número configurable de ciclos de enfoque consecuentes (por defecto, cada 4 ciclos). El LED brilla en color **Verde** progresivo. El display muestra el tiempo restante.
5.  **Fase de Alerta (ALERTA):** Al terminar cualquier fase de descanso, los LEDs destellan rápidamente en **Azul** (si terminó el descanso corto) o **Verde** (si terminó el descanso largo) acompañados de tonos acústicos del zumbador. Presionar el **Botón 1** inicia una nueva sesión Focus de inmediato.

---

## Gestos del Botón de Control (Botón 2)

El **Botón 2** permite controlar la sesión en tiempo de ejecución diferenciando tres gestos mediante temporización por software no bloqueante:
*   **Clic Simple:** Alterna entre Pausa y Reanudación del temporizador actual. Durante la pausa, el LED parpadeará suavemente en el color de la fase actual congelando su nivel de brillo actual.
*   **Doble Clic:** Reinicia el temporizador de la fase activa actual desde el principio (0s transcurridos).
*   **Presión Larga (mínimo 2 segundos):**
    *   *Durante una fase activa:* Resetea el ciclo completo y devuelve el sistema al estado **STANDBY**.

---

## Conectividad y Redes

*   **WiFi y Portal Cautivo:** Si no se encuentra un archivo `wifi.json` con credenciales, el ESP32 se inicia automáticamente en modo **Access Point / Portal Cautivo**, levantando un servidor web básico para configurar el SSID y la contraseña. Al conectarse exitosamente, guarda las credenciales y sincroniza los tiempos de Pomodoro con el backend.
*   **Sincronización Web REST:** El ESP32 consume un endpoint REST del servidor local al arrancar para sincronizar los parámetros de la sesión y envía peticiones HTTP POST asíncronas en segundo plano cada vez que se finaliza un ciclo.
*   **Soporte MQTT:** Envía reportes JSON a un broker MQTT (`pomodoro/sesiones`) en paralelo para telemetría.

---

## Inventario de Archivos en Uso

Todos los archivos del repositorio están activamente relacionados y desempeñan una función esencial:

### Firmware de la ESP32 (MicroPython)
*   [main.py](file:///Users/ivanbudnick/Documents/Pomodoro/main.py): Secuencia de arranque del chip, inicializa el Servidor HTTP y ejecuta el bucle de eventos principal no bloqueante.
*   [config.py](file:///Users/ivanbudnick/Documents/Pomodoro/config.py): Almacena los parámetros generales de pines, tiempos y constantes del sistema. Incluye los métodos para serializar/deserializar configuraciones y credenciales locales (`config.json` y `wifi.json`).
*   [pomodoro.py](file:///Users/ivanbudnick/Documents/Pomodoro/pomodoro.py): Controla la máquina de estados lógicos del Pomodoro, la transición entre fases, el apagado por inactividad (Deep Sleep) y los hilos para envío de reportes de red (HTTP/MQTT).
*   [hardware.py](file:///Users/ivanbudnick/Documents/Pomodoro/hardware.py): Driver de hardware. Maneja el control de brillo exponencial de los LEDs RGB basado en la entrada del fotoresistor LDR, tonos PWM del buzzer, la detección de gestos por debounce de botones, y la multiplexación de la pantalla de 7 segmentos.
*   [audio.py](file:///Users/ivanbudnick/Documents/Pomodoro/audio.py): Biblioteca de melodías y notificaciones sonoras integradas para retroalimentar las acciones del usuario (inicio, pausa, alerta, despertar de sleep, etc.).
*   [dashboard.html](file:///Users/ivanbudnick/Documents/Pomodoro/dashboard.html): Página web de control integrada en la ESP32 que se sirve directamente cuando se accede a su dirección IP desde el navegador.

### Servidor Dashboard y Herramientas PC (Python & Flask)
*   [backend/app.py](file:///Users/ivanbudnick/Documents/Pomodoro/backend/app.py): Backend Flask en la PC que mantiene una base de datos SQLite de telemetría, ofrece paneles estadísticos y expone APIs para la configuración de tiempos.
*   [backend/requirements.txt](file:///Users/ivanbudnick/Documents/Pomodoro/backend/requirements.txt): Declaración de dependencias del servidor backend (Flask, Paho-MQTT).

---

## Cómo Empezar

### 1. Iniciar el Servidor Flask en la PC
Instalá las dependencias y corre el servidor de estadísticas en tu PC:
```bash
pip install -r backend/requirements.txt
python backend/app.py
```
El panel estará disponible en [http://localhost:5001](http://localhost:5001).

### 2. Exponer el Servidor con Localtunnel (Opcional para Simulador Wokwi)
Si estás usando Wokwi y querés conectar el simulador a tu servidor local en la PC, exponé el puerto en una nueva terminal:
```bash
npx localtunnel --port 5001
```
Copia la URL `http` generada y configúrala en el parámetro `FLASK_SERVER_URL` de [config.py](file:///Users/ivanbudnick/Documents/Pomodoro/config.py) en tu ESP32/Wokwi.


