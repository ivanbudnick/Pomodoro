# Guía de Funcionamiento y Lógica del Pomodoro Pro (ESP32)

Este documento explica en detalle la máquina de estados, gestos del botón físico y flujo de telemetría de la ESP32 para que los desarrolladores de la plataforma `3D-Moai` comprendan el comportamiento esperado y puedan diseñar el dashboard de usuario y administrador.

---

## 1. Máquina de Estados del Dispositivo

El firmware de la ESP32 opera mediante una máquina de estados cooperativa no bloqueante con los siguientes estados:

| Estado (Código) | Comportamiento del LED RGB | Comportamiento del Buzzer | Descripción / Acciones asociadas |
| :--- | :--- | :--- | :--- |
| **STANDBY / IDLE** (0) | Parpadeo suave Amarillo (0.5s encendido / 0.5s apagado) | Silencioso | Estado de espera. Si transcurren **60 segundos** sin interacción física, la placa entra automáticamente en **Deep Sleep** para ahorrar batería. |
| **FOCUS** (1) | Luz Roja fija con rampa progresiva exponencial | Tono ascendente al iniciar | Fase de concentración. El brillo del LED aumenta según transcurre el tiempo (regulado por la fotoresistencia LDR para no molestar). |
| **DESCANSO CORTO** (2) | Luz Azul fija con rampa progresiva exponencial | Tono ascendente al iniciar | Fase de recreo corto (por defecto 5 min). El brillo del LED aumenta progresivamente. |
| **DESCANSO LARGO** (3) | Luz Verde fija con rampa progresiva exponencial | Tono ascendente al iniciar | Fase de recreo largo (por defecto 15 min). Ocurre cada $N$ ciclos de Focus consecutivos. |
| **ALERTA TITILANDO** (4) | Parpadeo rápido del color de la fase terminada (Rojo/Azul/Verde) | Pitidos intermitentes cortos | Fase de transición. Avisa al usuario que la fase actual concluyó. No se detiene hasta que el usuario realiza el gesto de confirmación (Clic Simple). |

---

## 2. Gestos del Botón Físico de Control

El Pomodoro cuenta con un **único botón físico** (con filtrado antirrebote por software) que interpreta los siguientes gestos del usuario:

* **Clic Simple**:
  * **En Standby**: Inicia la sesión de Focus (sincroniza parámetros de tiempos primero).
  * **En Alerta**: Detiene los pitidos/destellos y avanza al descanso o al siguiente Focus.
  * **En Fase Activa (Focus/Descanso)**: **Pausa** o **reanuda** el cronómetro.
* **Doble Clic**:
  * **En Fase Activa**: Omite (salta) el tiempo restante y avanza directamente a la Alerta de fin de fase.
* **Triple Clic**:
  * **En Fase Activa**: Reinicia el temporizador de la fase actual de vuelta a 0 (reseteo local de ciclo).
* **Mantener Presionado (2 segundos)**:
  * **En Cualquier Estado**: Interrumpe y cancela la sesión completa, reiniciando los contadores y devolviendo la placa al modo Standby (Luz Amarilla).

---

## 3. Lógica de Peticiones y Telemetría Web

La ESP32 encola todos sus eventos y los envía de manera **asíncrona en segundo plano** mediante un hilo secundario (`_telemetry_worker`) para no interrumpir el cronometraje ni causar retrasos en la luz o el sonido.

### A. Consultas de Configuración (`GET /api/pomodoro/config?device_id=...`)
Se gatilla de manera síncrona en dos momentos:
1. **Al encender la placa (Boot)**: Carga los tiempos iniciales. Si no hay internet, usa los últimos guardados en el disco local (`config.json`).
2. **Al pulsar Clic Simple para "Comenzar"**: Consulta la base de datos justo antes de iniciar la cuenta atrás para asegurar que inicia con los tiempos que el usuario modificó en la web.

### B. Registros de Estadísticas (`POST /api/pomodoro/stats`)
Cada llamada envía el identificador de hardware (`device_id`). El campo `tipo_sesion` clasifica el evento:

1. **Ciclo Completado**:
   * Ocurre al terminar de forma natural una fase y el usuario reaccionar a la alerta.
   * `tipo_sesion`: `'focus'`, `'descanso_corto'` o `'descanso_largo'`.
   * `duracion_s`: El tiempo total configurado (ej: 1500).
   * `forzado`: `0` (Completado).

2. **Ciclo Cancelado / Interrumpido**:
   * Ocurre cuando el usuario mantiene presionado el botón por 2s para volver a Standby.
   * `tipo_sesion`: `'focus'`, `'descanso_corto'` o `'descanso_largo'`.
   * `duracion_s`: Los segundos que el usuario llegó a estar activo en esa fase.
   * `forzado`: `1` (Interrumpido).

3. **Pausas**:
   * Ocurre cuando el usuario hace clic simple para pausar y luego reanudar.
   * `tipo_sesion`: `'pausa_focus'`, `'pausa_descanso_corto'` o `'pausa_descanso_largo'`.
   * `duracion_s`: La cantidad de segundos que el dispositivo estuvo en pausa.
   * `ciclo_num`: El tiempo transcurrido (en segundos) de la fase activa cuando se apretó pausa.

4. **Tiempo de Reacción a Alertas**:
   * Mide cuánto tarda el usuario en enterarse y apagar la alerta al finalizar un ciclo (útil para medir distracción).
   * `tipo_sesion`: `'reaccion_focus'`, `'reaccion_descanso_corto'` o `'reaccion_descanso_largo'`.
   * `duracion_s`: Tiempo en segundos (con decimales) transcurrido desde que la alerta empezó a sonar hasta que el usuario pulsó el botón.

---

## 4. Estructura de Visualización en el Dashboard (3D-Moai)

Con este esquema de telemetría, puedes implementar las siguientes métricas en tu panel de usuario:
* **Minutos de Enfoque Diarios**: Suma de `duracion_s` donde `tipo_sesion = 'focus'` y `forzado = 0` agrupado por día.
* **Tasa de Completitud**: Proporción de sesiones `focus` con `forzado = 0` vs `forzado = 1`.
* **Tiempo Promedio de Reacción**: Promedio de `duracion_s` en filas con `tipo_sesion` de tipo `reaccion_*`. Un menor tiempo de reacción indica mayor atención del usuario.
* **Rachas Activas**: Días consecutivos en el calendario que tengan al menos una fila de `focus` con `forzado = 0`.
