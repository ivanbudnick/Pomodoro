# ==============================================================================
# MÓDULO PRINCIPAL DE LA MÁQUINA DE ESTADOS POMODORO PRO
# ==============================================================================
# Este módulo implementa la lógica central del reloj Pomodoro Pro, estructurado
# como una Máquina de Estados Finitos (FSM) no bloqueante.
#
# La FSM cicla a través de los siguientes estados:
# 0. STANDBY: Espera pasiva (LED amarillo parpadeando).
# 1. FOCUS: Período de enfoque (LED rojo que aumenta su intensidad exponencialmente).
# 2. DESCANSO_CORTO: Pausa breve tras sesión focus (LED azul progresivo).
# 3. DESCANSO_LARGO: Pausa prolongada tras varios ciclos de enfoque (LED verde progresivo).
# 4. ALERTA: Notificación visual/auditiva al terminar un descanso, instando al reinicio.
#
# Conectividad:
# - Reporta automáticamente al servidor Flask local en la PC (vía HTTP o MQTT).
# - Envía y recibe datos en tiempo real mediante Bluetooth Low Energy (BLE).
# - Soporta entrada de gestos físicos (clic simple/doble, mantener presionado).

import time
import config
import hardware
import audio
import ble_uart

try:
    import urequests
except ImportError:
    urequests = None

try:
    from umqtt.simple import MQTTClient
except ImportError:
    MQTTClient = None

# --- ESTADOS DEL SISTEMA POMODORO PRO ---
ESTADO_STANDBY         = 0
ESTADO_FOCUS           = 1
ESTADO_DESCANSO_CORTO  = 2
ESTADO_DESCANSO_LARGO  = 3
ESTADO_ALERTA_TITILANDO = 4

NOMBRES_ESTADO = {
    ESTADO_STANDBY: "STANDBY",
    ESTADO_FOCUS: "FOCUS",
    ESTADO_DESCANSO_CORTO: "DESCANSO_CORTO",
    ESTADO_DESCANSO_LARGO: "DESCANSO_LARGO",
    ESTADO_ALERTA_TITILANDO: "ALERTA"
}

# --- VARIABLES DE ESTADO GLOBALES ---
estado_actual = ESTADO_STANDBY
cronometro = time.ticks_ms()        # Marca de tiempo de inicio del estado o tick actual
ultimo_titilo = time.ticks_ms()      # Control de tiempo para parpadeos de LEDs
estado_luz_titilo = False           # Estado ON/OFF intermitente del parpadeo
ciclos_focus_consecutivos = 0       # Contador de sesiones FOCUS finalizadas con éxito
ultimo_evento_ms = time.ticks_ms()  # Control de inactividad para entrar en Deep Sleep
color_alerta_actual = "azul"        # Color contextual de la alerta (azul o verde)

# Variables de control del temporizador de pausa
pausado = False
tiempo_acumulado_ms = 0             # Tiempo ya transcurrido de la fase antes de pausar

# --- CONFIGURACIÓN Y VARIABLES DE ESTADO BLE ---
ble_dispositivo = None
ultimo_estado_ble = -1
ultimo_segundo_ble = -1
ultimo_pausado_ble = None
ble_anunciando = False

# ==============================================================================
# FUNCIONES DE REPORTERÍA (MQTT & REST FLASK)
# ==============================================================================

def enviar_reporte_mqtt(tipo_sesion, ciclo_num, duracion_s):
    """
    Intenta publicar un JSON con la sesión completada al Broker MQTT.
    Retorna True si tiene éxito y False si hay fallas de red/conexión.
    """
    if MQTTClient is None:
        print("[MQTT REPORT WARNING] Modulo umqtt.simple no está disponible.")
        return False
    try:
        import ujson as json
        
        client = MQTTClient("esp32_pomodoro_client", config.MQTT_BROKER, port=config.MQTT_PORT)
        client.connect()
        
        payload = json.dumps({
            "dispositivo": "ESP32_Pomodoro",
            "tipo_sesion": tipo_sesion,
            "ciclo_num": ciclo_num,
            "duracion_s": duracion_s
        })
        
        client.publish(config.MQTT_TOPIC_SESIONES, payload)
        client.disconnect()
        print("[MQTT REPORT] Sesión '{}' (#{}) enviada exitosamente por MQTT.".format(tipo_sesion, ciclo_num))
        return True
    except Exception as e:
        print("[MQTT REPORT WARNING] No se pudo enviar reporte por MQTT ({}). Intentando fallback por HTTP...".format(e))
        return False

def _enviar_reporte_thread(tipo_sesion, ciclo_num, duracion_s):
    """
    Subfunción interna ejecutada en segundo plano para realizar el envío.
    Intenta primero HTTP (al ser IP local, es instantáneo y evita DNS lookup).
    Si falla, intenta MQTT como fallback.
    """
    try:
        # 1. Intentar HTTP POST local (IP directa, sin DNS)
        if urequests is not None:
            try:
                payload = {
                    "dispositivo": "ESP32_Pomodoro",
                    "evento": "sesion_completada",
                    "tipo_sesion": tipo_sesion,
                    "ciclo_num": ciclo_num,
                    "duracion_s": duracion_s
                }
                res = urequests.post(config.FLASK_SERVER_URL, json=payload)
                print("[FLASK REPORT] Sesión '{}' (#{}) enviada a la PC. HTTP: {}".format(tipo_sesion, ciclo_num, res.status_code))
                res.close()
                return  # Éxito, salir de la función
            except Exception as e:
                print("[FLASK REPORT WARNING] No se pudo enviar por HTTP local:", e)
        else:
            print("[FLASK REPORT WARNING] Modulo urequests no disponible.")
            
        # 2. Fallback: Intentar MQTT (requiere DNS lookup de broker.hivemq.com)
        enviar_reporte_mqtt(tipo_sesion, ciclo_num, duracion_s)
    finally:
        import gc
        gc.collect()

def enviar_reporte_flask(tipo_sesion, ciclo_num, duracion_s):
    """
    Registra el fin de una sesión de forma remota en la base de datos de la PC.
    Para evitar bloquear el bucle principal (lo que causaría demoras en el paso
    de fases y parpadeo errático del display de 7 segmentos), esta operación
    de red se delega a un hilo de fondo asíncrono.
    """
    try:
        import _thread
        _thread.start_new_thread(_enviar_reporte_thread, (tipo_sesion, ciclo_num, duracion_s))
    except Exception as e:
        print("[THREAD ERROR] No se pudo iniciar hilo de reporte ({}). Ejecutando síncrono...".format(e))
        _enviar_reporte_thread(tipo_sesion, ciclo_num, duracion_s)

# ==============================================================================
# HELPERS DE TEMPORIZACIÓN (OPTIMIZACIÓN DE CÓDIGO)
# ==============================================================================

def obtener_segundos_restantes(ahora=None):
    """
    Helper centralizado para calcular el tiempo restante en segundos de la fase activa actual.
    Evita código duplicado en la visualización física, peticiones web y reportes BLE.
    """
    if ahora is None:
        ahora = time.ticks_ms()
        
    if estado_actual not in (ESTADO_FOCUS, ESTADO_DESCANSO_CORTO, ESTADO_DESCANSO_LARGO):
        return 0
        
    if estado_actual == ESTADO_FOCUS:
        duracion_ms = config.tiempo_focus_s * 1000
    elif estado_actual == ESTADO_DESCANSO_CORTO:
        duracion_ms = config.tiempo_descanso_corto_s * 1000
    else:  # ESTADO_DESCANSO_LARGO
        duracion_ms = config.tiempo_descanso_largo_s * 1000
        
    transcurrido = tiempo_acumulado_ms
    if not pausado:
        transcurrido += time.ticks_diff(ahora, cronometro)
        
    return max(0, int((duracion_ms - transcurrido) / 1000))

# ==============================================================================
# INTEGRACIÓN BLUETOOTH BLE
# ==============================================================================

def inicializar_ble():
    """Instancia el servidor BLE y prepara los descriptores GATT"""
    global ble_dispositivo
    import gc
    gc.collect()
    try:
        ble_dispositivo = ble_uart.BLEUART("Pomodoro-ESP32")
        print("[BLE] Servidor inicializado con éxito.")
    except Exception as e:
        print("[BLE ERROR] No se pudo inicializar BLE:", e)

def desactivar_ble():
    """Desactiva por completo el módulo BLE y libera sus recursos de memoria"""
    global ble_dispositivo
    if ble_dispositivo is not None:
        try:
            ble_dispositivo.detener_anuncios()
            ble_dispositivo._ble.active(False)
            print("[BLE] Dispositivo desactivado por completo.")
        except Exception as e:
            print("[BLE ERROR] Error al desactivar BLE:", e)
        finally:
            ble_dispositivo = None
            import gc
            gc.collect()

def procesar_comandos_ble():
    """
    Monitorea el puerto serie virtual Bluetooth BLE.
    Decodifica strings entrantes e interrumpe el flujo normal simulando eventos físicos.
    """
    global ble_dispositivo
    if not ble_dispositivo or not ble_dispositivo.any():
        return None
    try:
        raw_cmd = ble_dispositivo.read()
        cmd = raw_cmd.decode('utf-8').strip().upper()
        print("[BLE RX COMANDO]: {}".format(cmd))
        
        # Cualquier comando Bluetooth reactiva el temporizador de inactividad
        registrar_actividad()
        
        if cmd in ("PAUSE", "PLAY", "TOGGLE"):
            return "PAUSA"
        elif cmd in ("RESET_FASE", "RESET"):
            return "RESET_FASE"
        elif cmd in ("STANDBY", "RESET_IDLE"):
            return "RESET_IDLE"
        elif cmd == "START":
            return "START"
    except Exception as e:
        print("[BLE RX ERROR] Error al decodificar comando:", e)
    return None

def enviar_estado_ble(forzar=False):
    """
    Transmite el estado interno formateado en texto de baja latencia vía BLE.
    Solo envía el paquete si hay un cambio real en el estado, pausa o tiempo
    para evitar congestionar el aire (polling pasivo).
    """
    global ble_dispositivo, ultimo_estado_ble, ultimo_segundo_ble, ultimo_pausado_ble
    if not ble_dispositivo or not ble_dispositivo.esta_conectado():
        return
        
    ahora = time.ticks_ms()
    remaining_s = obtener_segundos_restantes(ahora)
        
    if (forzar or 
        estado_actual != ultimo_estado_ble or 
        remaining_s != ultimo_segundo_ble or 
        pausado != ultimo_pausado_ble):
        
        pausado_val = 1 if pausado else 0
        # Formato optimizado (<20 bytes): S:<estado>,<pausado>,<segundos_restantes>,<ciclos_completados>\n
        payload = "S:{},{},{},{}\n".format(estado_actual, pausado_val, remaining_s, ciclos_focus_consecutivos)
        try:
            ble_dispositivo.write(payload)
            ultimo_estado_ble = estado_actual
            ultimo_segundo_ble = remaining_s
            ultimo_pausado_ble = pausado
        except Exception as e:
            print("[BLE TX ERROR] No se pudo enviar estado:", e)

def obtener_dict_estado():
    """Construye un JSON/Diccionario descriptivo del estado actual para la API HTTP"""
    ahora = time.ticks_ms()
    nombre = NOMBRES_ESTADO.get(estado_actual, "DESCONOCIDO")
    remaining_s = obtener_segundos_restantes(ahora)
        
    return {
        "estado": estado_actual,
        "estado_nombre": nombre,
        "remaining_s": remaining_s,
        "tiempo_focus": config.tiempo_focus_s,
        "tiempo_descanso_corto": config.tiempo_descanso_corto_s,
        "tiempo_descanso_largo": config.tiempo_descanso_largo_s,
        "descanso_largo_activo": config.descanso_largo_activo,
        "ciclos_para_descanso_largo": config.ciclos_para_descanso_largo,
        "ciclos_focus_completados": ciclos_focus_consecutivos,
        "pausado": pausado
    }

# ==============================================================================
# SUB-FUNCIONES MODULARIZADAS DE LA MÁQUINA DE ESTADOS
# ==============================================================================

def _procesar_entradas_y_gestos(ahora, botón_pulsado, gesto, gesto_ble):
    """Prioriza y procesa los comandos físicos y digitales"""
    start_requested = botón_pulsado
    if gesto_ble == "START" and estado_actual in (ESTADO_STANDBY, ESTADO_ALERTA_TITILANDO):
        start_requested = True
        
    gesto_resuelto = gesto
    if gesto_ble == "PAUSA":
        gesto_resuelto = hardware.GESTO_PAUSA
    elif gesto_ble == "RESET_FASE":
        gesto_resuelto = hardware.GESTO_RESET_FASE
    elif gesto_ble == "RESET_IDLE":
        gesto_resuelto = hardware.GESTO_RESET_IDLE
        
    return gesto_resuelto, start_requested

def _manejar_parpadeo_pausa(ahora):
    """Hace parpadear el LED en el color de la fase actual y con su brillo congelado"""
    global ultimo_titilo, estado_luz_titilo
    hardware.sonar_buzzer(0, False)
    
    if time.ticks_diff(ahora, ultimo_titilo) >= 500:
        estado_luz_titilo = not estado_luz_titilo
        if estado_luz_titilo:
            if estado_actual == ESTADO_FOCUS:
                duracion_ms = config.tiempo_focus_s * 1000
            elif estado_actual == ESTADO_DESCANSO_CORTO:
                duracion_ms = config.tiempo_descanso_corto_s * 1000
            else:
                duracion_ms = config.tiempo_descanso_largo_s * 1000
                
            intensidad = hardware.calcular_intensidad_progresiva(tiempo_acumulado_ms, duracion_ms)
            
            if estado_actual == ESTADO_FOCUS:
                hardware.set_color_pwm(intensidad, 0, 0)
            elif estado_actual == ESTADO_DESCANSO_CORTO:
                hardware.set_color_pwm(0, 0, intensidad)
            elif estado_actual == ESTADO_DESCANSO_LARGO:
                hardware.set_color_pwm(0, intensidad, 0)
        else:
            hardware.set_color_pwm(0, 0, 0)
        ultimo_titilo = ahora

def _ejecutar_estado_standby(ahora, start_requested):
    """Bucle inactivo: Hace parpadear una luz amarilla suave esperando inicio"""
    global estado_actual, cronometro, tiempo_acumulado_ms, pausado, ultimo_titilo, estado_luz_titilo
    hardware.sonar_buzzer(0, False)
            
    if time.ticks_diff(ahora, ultimo_titilo) >= config.INTERVALO_TITILO_STANDBY_MS:
        estado_luz_titilo = not estado_luz_titilo
        if estado_luz_titilo:
            hardware.set_color_pwm(config.DUTY_MAX, config.DUTY_MAX, 0)
        else:
            hardware.set_color_pwm(0, 0, 0)
        ultimo_titilo = ahora
        
    if start_requested:
        cronometro = ahora
        tiempo_acumulado_ms = 0
        pausado = False
        estado_actual = ESTADO_FOCUS
        print("[POMODORO] Inicio Sesión FOCUS ({}s).".format(config.tiempo_focus_s))
        audio.play_start_cold()
        time.sleep_ms(config.DEBOUNCE_BOTON_MS)

def _ejecutar_estado_focus(ahora):
    """Fase activa de enfoque: Modula la luz roja en rampa exponencial progresiva"""
    global estado_actual, cronometro, tiempo_acumulado_ms, ciclos_focus_consecutivos
    hardware.sonar_buzzer(0, False)
    
    transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
    duracion_ms = config.tiempo_focus_s * 1000
    intensidad_rojo = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
    
    hardware.set_color_pwm(intensidad_rojo, 0, 0)
    
    if transcurrido >= duracion_ms:
        ciclos_focus_consecutivos += 1
        print("[POMODORO] ¡Sesión FOCUS #{} Completada! ({}s)".format(ciclos_focus_consecutivos, config.tiempo_focus_s))
        audio.play_done_focus()
        enviar_reporte_flask("focus", ciclos_focus_consecutivos, config.tiempo_focus_s)
        
        cronometro = ahora
        tiempo_acumulado_ms = 0
        
        # Determinar si corresponde ir a descanso largo o corto
        es_descanso_largo = (
            config.descanso_largo_activo and 
            (ciclos_focus_consecutivos % max(2, config.ciclos_para_descanso_largo) == 0)
        )
        
        if es_descanso_largo:
            estado_actual = ESTADO_DESCANSO_LARGO
            print("[POMODORO] Inicio DESCANSO LARGO (LED Verde, {}s).".format(config.tiempo_descanso_largo_s))
        else:
            estado_actual = ESTADO_DESCANSO_CORTO
            print("[POMODORO] Inicio DESCANSO CORTO (LED Azul, {}s).".format(config.tiempo_descanso_corto_s))

def _ejecutar_estado_descanso_corto(ahora):
    """Fase de descanso corto: Modula la luz azul en rampa exponencial progresiva"""
    global estado_actual, cronometro, tiempo_acumulado_ms, ultimo_titilo, estado_luz_titilo, color_alerta_actual
    
    transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
    duracion_ms = config.tiempo_descanso_corto_s * 1000
    intensidad_azul = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
    
    hardware.set_color_pwm(0, 0, intensidad_azul)
    
    if transcurrido >= duracion_ms:
        hardware.set_color_pwm(0, 0, 0)
        audio.play_done_break()
        enviar_reporte_flask("descanso_corto", ciclos_focus_consecutivos, config.tiempo_descanso_corto_s)
        
        cronometro = ahora
        tiempo_acumulado_ms = 0
        ultimo_titilo = time.ticks_ms()
        estado_luz_titilo = True
        color_alerta_actual = "azul"
        estado_actual = ESTADO_ALERTA_TITILANDO
        print("[POMODORO] Fin Descanso Corto. Estado: Alerta (Azul).")

def _ejecutar_estado_descanso_largo(ahora):
    """Fase de descanso largo: Modula la luz verde en rampa exponencial progresiva"""
    global estado_actual, cronometro, tiempo_acumulado_ms, ultimo_titilo, estado_luz_titilo, color_alerta_actual
    
    transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
    duracion_ms = config.tiempo_descanso_largo_s * 1000
    intensidad_verde = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
    
    hardware.set_color_pwm(0, intensidad_verde, 0)
    
    if transcurrido >= duracion_ms:
        hardware.set_color_pwm(0, 0, 0)
        audio.play_done_break()
        enviar_reporte_flask("descanso_largo", ciclos_focus_consecutivos, config.tiempo_descanso_largo_s)
        
        cronometro = ahora
        tiempo_acumulado_ms = 0
        ultimo_titilo = time.ticks_ms()
        estado_luz_titilo = True
        color_alerta_actual = "verde"
        estado_actual = ESTADO_ALERTA_TITILANDO
        print("[POMODORO] Fin Descanso Largo. Estado: Alerta (Verde).")

def _ejecutar_estado_alerta(ahora, start_requested):
    """El temporizador finalizó: Destella la luz con pitidos cortos e intermitentes"""
    global estado_actual, cronometro, tiempo_acumulado_ms, pausado, ultimo_titilo, estado_luz_titilo
    
    if time.ticks_diff(ahora, ultimo_titilo) >= config.INTERVALO_ALERTA_MS:
        estado_luz_titilo = not estado_luz_titilo
        if estado_luz_titilo:
            if color_alerta_actual == "verde":
                hardware.set_color_pwm(0, config.DUTY_MAX, 0)
            else:
                hardware.set_color_pwm(0, 0, config.DUTY_MAX)
            audio.play_alert_pip()
        else:
            hardware.set_color_pwm(0, 0, 0)
            hardware.sonar_buzzer(0, False)
        ultimo_titilo = ahora
        
    if start_requested:
        hardware.sonar_buzzer(0, False)
        cronometro = ahora
        tiempo_acumulado_ms = 0
        pausado = False
        estado_actual = ESTADO_FOCUS
        print("[POMODORO] Reinicio. Inicio Sesión FOCUS ({}s).".format(config.tiempo_focus_s))
        audio.play_start_warm()
        time.sleep_ms(config.DEBOUNCE_BOTON_MS)

def _actualizar_display_siete_segmentos(ahora):
    """Determina la representación del tiempo o estado en la pantalla"""
    if ble_anunciando and ble_dispositivo is not None and not ble_dispositivo.esta_conectado() and estado_actual == ESTADO_STANDBY:
        # Si Bluetooth está activo y sin conectar en Standby, muestra "bLE" para avisar disponibilidad
        hardware.display.mostrar_texto("bLE ")
    elif estado_actual == ESTADO_STANDBY or estado_actual == ESTADO_ALERTA_TITILANDO:
        hardware.display.mostrar_texto("----")
    else:
        ocultar = (estado_actual != ESTADO_FOCUS)
        remaining_s = obtener_segundos_restantes(ahora)
        hardware.display.mostrar_pomodoro(remaining_s, ciclos_focus_consecutivos, ocultar_vueltas=ocultar)

# ==============================================================================
# INTERFAZ PÚBLICA DEL MÓDULO
# ==============================================================================

def ejecutar_pomodoro_step():
    """
    Tick periódico de la máquina de estados.
    Es llamado desde el loop principal en main.py en cada iteración.
    Ejecuta comprobaciones de gestos y calcula las trancisiones de la FSM de manera no bloqueante.
    """
    global estado_actual, cronometro, ultimo_titilo, estado_luz_titilo, ciclos_focus_consecutivos, pausado, tiempo_acumulado_ms
    
    ahora = time.ticks_ms()
    botón_pulsado = hardware.boton_presionado()
    gesto = hardware.detectar_gesto_boton_control()
    gesto_ble = procesar_comandos_ble()
    
    gesto_resuelto, start_requested = _procesar_entradas_y_gestos(ahora, botón_pulsado, gesto, gesto_ble)
    
    # Registrar actividad del usuario para prolongar el tiempo antes de entrar a hibernar
    if ((estado_actual != ESTADO_STANDBY and not pausado) or 
            botón_pulsado or 
            (gesto != hardware.GESTO_NINGUNO) or 
            (gesto_ble is not None)):
        registrar_actividad()
    
    # GESTO MANTENER: Reset total al modo de espera (Standby) o conmutación BLE si ya estamos en Standby
    if gesto_resuelto == hardware.GESTO_RESET_IDLE:
        if estado_actual == ESTADO_STANDBY:
            # Conmutar (Toggle) anuncios Bluetooth BLE (evitando ENOMEM ya que el objeto BLE se crea en el boot)
            if not ble_anunciando:
                # Encender anuncios Bluetooth (Pairing)
                hardware.display.mostrar_texto("bLE ")
                hardware.set_color_pwm(0, 0, config.DUTY_MAX) # Azul brillante
                audio.play_resume() # Pitido de éxito
                
                iniciar_anuncios()
                
                # Esperar a que el usuario suelte el botón para no registrar más pulsaciones
                while hardware.btn_control.value() == 0:
                    time.sleep_ms(10)
                hardware.reset_gestos()
            else:
                # Apagar anuncios Bluetooth
                hardware.display.mostrar_texto("oFF ")
                hardware.set_color_pwm(0, 0, 0)
                audio.play_reset_idle() # Pitido de apagado
                
                detener_anuncios()
                
                # Apagar el LED interno
                hardware.set_led_interno(False)
                
                # Esperar a que el usuario suelte el botón
                while hardware.btn_control.value() == 0:
                    time.sleep_ms(10)
                hardware.reset_gestos()
            return
        else:
            audio.play_reset_idle()
            estado_actual = ESTADO_STANDBY
            pausado = False
            tiempo_acumulado_ms = 0
            ciclos_focus_consecutivos = 0
            ultimo_titilo = ahora
            print("[POMODORO] Reset total. Regreso a STANDBY. Ciclos de descanso reiniciados.")
            return

    # GESTOS EN TIEMPO DE FASE: Pausa y Reset local de fase
    if estado_actual != ESTADO_STANDBY and estado_actual != ESTADO_ALERTA_TITILANDO:
        # Doble clic -> Reiniciar temporizador de fase actual a 0s
        if gesto_resuelto == hardware.GESTO_RESET_FASE:
            cronometro = ahora
            tiempo_acumulado_ms = 0
            pausado = False
            audio.play_reset_phase()
            print("[POMODORO] Fase actual reseteada a 0s.")
            return

        # Clic simple -> Alternar Pausa/Reanudación
        if gesto_resuelto == hardware.GESTO_PAUSA:
            pausado = not pausado
            if pausado:
                tiempo_acumulado_ms += time.ticks_diff(ahora, cronometro)
                print("[POMODORO] Temporizador PAUSADO.")
                audio.play_pause()
            else:
                cronometro = ahora
                print("[POMODORO] Temporizador REANUDADO.")
                audio.play_resume()
            return

    # Si está en pausa, titilar suavemente manteniendo el brillo estático y retornar
    if pausado and estado_actual != ESTADO_STANDBY and estado_actual != ESTADO_ALERTA_TITILANDO:
        _manejar_parpadeo_pausa(ahora)
        return

    # Ejecutar lógica del estado actual
    if estado_actual == ESTADO_STANDBY:
        _ejecutar_estado_standby(ahora, start_requested)
    elif estado_actual == ESTADO_FOCUS:
        _ejecutar_estado_focus(ahora)
    elif estado_actual == ESTADO_DESCANSO_CORTO:
        _ejecutar_estado_descanso_corto(ahora)
    elif estado_actual == ESTADO_DESCANSO_LARGO:
        _ejecutar_estado_descanso_largo(ahora)
    elif estado_actual == ESTADO_ALERTA_TITILANDO:
        _ejecutar_estado_alerta(ahora, start_requested)
        
    _actualizar_display_siete_segmentos(ahora)
    enviar_estado_ble()

def registrar_actividad():
    """Guarda una marca de tiempo con la última pulsación o comando recibido"""
    global ultimo_evento_ms
    ultimo_evento_ms = time.ticks_ms()

def verificar_y_ejecutar_sleep():
    """
    Evalúa la inactividad en el estado STANDBY. Si expira el tiempo configurado,
    configura la interrupción por pin externo (wake_on_ext0) para el botón principal
    (GPIO 25) y entra en el modo Deep Sleep (ultra bajo consumo).
    """
    global estado_actual, ultimo_evento_ms
    if estado_actual == ESTADO_STANDBY:
        ahora = time.ticks_ms()
        transcurrido_ms = time.ticks_diff(ahora, ultimo_evento_ms)
        if transcurrido_ms >= config.TIEMPO_INACTIVIDAD_SLEEP_MS:
            print("[SLEEP] Pomodoro inactivo por {}s. Entrando en Deep Sleep...".format(transcurrido_ms // 1000))
            
            audio.play_sleep_in()
            hardware.set_color_pwm(0, 0, 0)
            hardware.display.detener()
            
            # Preparar pin para disparar el despertar lógico por flanco descendente (0)
            import machine
            import esp32
            
            wake_pin = machine.Pin(config.PIN_BTN, machine.Pin.IN, machine.Pin.PULL_UP)
            esp32.wake_on_ext0(pin=wake_pin, level=0)
            
            # Entrar en deepsleep (se reiniciará el programa al despertar)
            machine.deepsleep()

def detener_anuncios():
    """Detiene las transmisiones de anuncios BLE para liberar la radio RF."""
    global ble_dispositivo, ble_anunciando
    if ble_dispositivo:
        try:
            ble_dispositivo.detener_anuncios()
            ble_anunciando = False
        except Exception as e:
            print("[BLE ERROR] No se pudieron detener anuncios:", e)

def iniciar_anuncios():
    """Reactiva las transmisiones de anuncios BLE."""
    global ble_dispositivo, ble_anunciando
    if ble_dispositivo:
        try:
            ble_dispositivo.iniciar_anuncios()
            ble_anunciando = True
        except Exception as e:
            print("[BLE ERROR] No se pudieron iniciar anuncios:", e)
