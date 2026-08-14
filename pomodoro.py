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
# - Soporta entrada de gestos físicos (clic simple/doble, mantener presionado).

import time
import config
import hardware
import audio

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

# --- CONFIGURACIÓN Y VARIABLES DE ESTADO AUXILIARES ---
siguiente_estado_descanso = None
inicio_alerta_ms = 0
inicio_pausa_ms = 0


# --- HELPERS Y FUNCIONES DE TELEMETRÍA (METRICAS) ---
def obtener_nombre_fase(estado):
    if estado == ESTADO_FOCUS:
        return "FOCUS"
    elif estado == ESTADO_DESCANSO_CORTO:
        return "DESCANSO_CORTO"
    elif estado == ESTADO_DESCANSO_LARGO:
        return "DESCANSO_LARGO"
    return "STANDBY"

def reportar_ciclo(fase, evento, tiempo, forzado=0):
    try:
        config.enviar_reporte_ciclo(fase, evento, tiempo, forzado)
    except:
        pass

def reportar_pausa(fase, tiempo_transcurrido_s, porcentaje, duracion_pausa_s):
    try:
        config.enviar_reporte_pausa(fase, tiempo_transcurrido_s, porcentaje, duracion_pausa_s)
    except:
        pass

def reportar_reaccion(tipo_alerta, duracion_alerta_s):
    try:
        config.enviar_reporte_reaccion(tipo_alerta, duracion_alerta_s)
    except:
        pass

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

def enviar_reporte_nube(tipo_sesion, ciclo_num, duracion_s, forzado=0):
    """
    Registra el fin de una sesión de forma remota en la base de datos de la nube (3D-Moai).
    Encolado de forma asíncrona para evitar pausas en el bucle principal.
    """
    try:
        payload = {
            "device_id": config.DEVICE_ID,
            "tipo_sesion": tipo_sesion,
            "ciclo_num": ciclo_num,
            "duracion_s": duracion_s,
            "forzado": forzado
        }
        config.encolar_telemetria(config.SERVER_URL + "/api/pomodoro/stats", payload)
        print("[NUBE REPORT] Sesión '{}' (#{}) encolada para envío.".format(tipo_sesion, ciclo_num))
    except Exception as e:
        print("[NUBE REPORT ERROR] Error al encolar reporte:", e)

# ==============================================================================
# HELPERS DE TEMPORIZACIÓN (OPTIMIZACIÓN DE CÓDIGO)
# ==============================================================================
def obtener_segundos_restantes(ahora=None):
    """
    Helper centralizado para calcular el tiempo restante en segundos de la fase activa actual.
    Evita código duplicado en la visualización física y peticiones web.
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
        # Sincronizar configuraciones de tiempos desde Vercel justo al presionar comenzar
        try:
            print("[STANDBY] Presionado comenzar. Sincronizando configuraciones...")
            config.sincronizar_config()
        except Exception as e:
            print("[STANDBY WARNING] Fallo al sincronizar configuración:", e)

        config.print_configuracion_actual()

        cronometro = ahora
        tiempo_acumulado_ms = 0
        pausado = False
        estado_actual = ESTADO_FOCUS
        print("[POMODORO] Inicio Sesión FOCUS ({}s).".format(config.tiempo_focus_s))
        reportar_ciclo("FOCUS", "INICIADO", 0)
        audio.play_start_cold()
        time.sleep_ms(config.DEBOUNCE_BOTON_MS)

def _ejecutar_estado_focus(ahora):
    """Fase activa de enfoque: Modula la luz roja en rampa exponencial progresiva"""
    global estado_actual, cronometro, tiempo_acumulado_ms, ciclos_focus_consecutivos, color_alerta_actual, siguiente_estado_descanso, inicio_alerta_ms, ultimo_titilo, estado_luz_titilo
    hardware.sonar_buzzer(0, False)
    
    transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
    duracion_ms = config.tiempo_focus_s * 1000
    intensidad_rojo = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
    
    hardware.set_color_pwm(intensidad_rojo, 0, 0)
    
    if transcurrido >= duracion_ms:
        ciclos_focus_consecutivos += 1
        print("[POMODORO] ¡Sesión FOCUS #{} Completada! ({}s)".format(ciclos_focus_consecutivos, config.tiempo_focus_s))
        audio.play_done_focus()
        enviar_reporte_nube("focus", ciclos_focus_consecutivos, config.tiempo_focus_s)
        
        # Reportar completado del FOCUS
        reportar_ciclo("FOCUS", "COMPLETADO", config.tiempo_focus_s)
        
        cronometro = ahora
        tiempo_acumulado_ms = 0
        
        # Determinar si corresponde ir a descanso largo o corto
        es_descanso_largo = (
            config.descanso_largo_activo and 
            (ciclos_focus_consecutivos % max(2, config.ciclos_para_descanso_largo) == 0)
        )
        
        if es_descanso_largo:
            siguiente_estado_descanso = ESTADO_DESCANSO_LARGO
        else:
            siguiente_estado_descanso = ESTADO_DESCANSO_CORTO
            
        color_alerta_actual = "rojo"
        inicio_alerta_ms = ahora
        ultimo_titilo = ahora
        estado_luz_titilo = True
        estado_actual = ESTADO_ALERTA_TITILANDO
        print("[POMODORO] Fin Focus. Esperando confirmación para iniciar descanso (Alerta Roja).")

def _ejecutar_estado_descanso_corto(ahora):
    """Fase de descanso corto: Modula la luz azul en rampa exponencial progresiva"""
    global estado_actual, cronometro, tiempo_acumulado_ms, ultimo_titilo, estado_luz_titilo, color_alerta_actual, inicio_alerta_ms
    
    transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
    duracion_ms = config.tiempo_descanso_corto_s * 1000
    intensidad_azul = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
    
    hardware.set_color_pwm(0, 0, intensidad_azul)
    
    if transcurrido >= duracion_ms:
        hardware.set_color_pwm(0, 0, 0)
        audio.play_done_break()
        enviar_reporte_nube("descanso_corto", ciclos_focus_consecutivos, config.tiempo_descanso_corto_s)
        
        # Reportar completado del descanso corto
        reportar_ciclo("DESCANSO_CORTO", "COMPLETADO", config.tiempo_descanso_corto_s)
        
        cronometro = ahora
        tiempo_acumulado_ms = 0
        ultimo_titilo = ahora
        estado_luz_titilo = True
        color_alerta_actual = "azul"
        inicio_alerta_ms = ahora
        estado_actual = ESTADO_ALERTA_TITILANDO
        print("[POMODORO] Fin Descanso Corto. Estado: Alerta (Azul).")

def _ejecutar_estado_descanso_largo(ahora):
    """Fase de descanso largo: Modula la luz verde en rampa exponencial progresiva"""
    global estado_actual, cronometro, tiempo_acumulado_ms, ultimo_titilo, estado_luz_titilo, color_alerta_actual, inicio_alerta_ms
    
    transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
    duracion_ms = config.tiempo_descanso_largo_s * 1000
    intensidad_verde = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
    
    hardware.set_color_pwm(0, intensidad_verde, 0)
    
    if transcurrido >= duracion_ms:
        hardware.set_color_pwm(0, 0, 0)
        audio.play_done_break()
        enviar_reporte_nube("descanso_largo", ciclos_focus_consecutivos, config.tiempo_descanso_largo_s)
        
        # Reportar completado del descanso largo
        reportar_ciclo("DESCANSO_LARGO", "COMPLETADO", config.tiempo_descanso_largo_s)
        
        cronometro = ahora
        tiempo_acumulado_ms = 0
        ultimo_titilo = ahora
        estado_luz_titilo = True
        color_alerta_actual = "verde"
        inicio_alerta_ms = ahora
        estado_actual = ESTADO_ALERTA_TITILANDO
        print("[POMODORO] Fin Descanso Largo. Estado: Alerta (Verde).")

def _ejecutar_estado_alerta(ahora, start_requested):
    """El temporizador finalizó: Destella la luz con pitidos cortos e intermitentes"""
    global estado_actual, cronometro, tiempo_acumulado_ms, pausado, ultimo_titilo, estado_luz_titilo, color_alerta_actual
    
    if time.ticks_diff(ahora, ultimo_titilo) >= config.INTERVALO_ALERTA_MS:
        estado_luz_titilo = not estado_luz_titilo
        if estado_luz_titilo:
            if color_alerta_actual == "verde":
                hardware.set_color_pwm(0, config.DUTY_MAX, 0)
                audio.play_alert_pip()
            elif color_alerta_actual == "azul":
                hardware.set_color_pwm(0, 0, config.DUTY_MAX)
                audio.play_alert_pip()
            elif color_alerta_actual == "rojo":
                # Alerta roja post-focus (parpadeo rojo)
                hardware.set_color_pwm(config.DUTY_MAX, 0, 0)
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
        
        # Calcular y reportar tiempo de reacción
        duracion_alerta_s = time.ticks_diff(ahora, inicio_alerta_ms) / 1000.0
        
        if color_alerta_actual == "rojo":
            # Salimos de alerta roja (post-focus) al descanso correspondiente
            reportar_reaccion("POST_FOCUS", duracion_alerta_s)
            
            estado_actual = siguiente_estado_descanso
            if estado_actual == ESTADO_DESCANSO_LARGO:
                print("[POMODORO] Inicio DESCANSO LARGO (LED Verde, {}s).".format(config.tiempo_descanso_largo_s))
                reportar_ciclo("DESCANSO_LARGO", "INICIADO", 0)
            else:
                print("[POMODORO] Inicio DESCANSO CORTO (LED Azul, {}s).".format(config.tiempo_descanso_corto_s))
                reportar_ciclo("DESCANSO_CORTO", "INICIADO", 0)
        else:
            # Salimos de alerta post-descanso a una nueva sesión de Focus
            tipo_alerta = "POST_DESCANSO_LARGO" if color_alerta_actual == "verde" else "POST_DESCANSO_CORTO"
            reportar_reaccion(tipo_alerta, duracion_alerta_s)
            
            estado_actual = ESTADO_FOCUS
            print("[POMODORO] Reinicio. Inicio Sesión FOCUS ({}s).".format(config.tiempo_focus_s))
            reportar_ciclo("FOCUS", "INICIADO", 0)
            
        audio.play_start_warm()
        time.sleep_ms(config.DEBOUNCE_BOTON_MS)

# ==============================================================================
# INTERFAZ PÚBLICA DEL MÓDULO
# ==============================================================================

def ejecutar_pomodoro_step():
    """
    Tick periódico de la máquina de estados.
    Es llamado desde el loop principal en main.py en cada iteración.
    Ejecuta comprobaciones de gestos y calcula las trancisiones de la FSM de manera no bloqueante.
    """
    global estado_actual, cronometro, ultimo_titilo, estado_luz_titilo, ciclos_focus_consecutivos, pausado, tiempo_acumulado_ms, inicio_pausa_ms
    
    ahora = time.ticks_ms()
    botón_pulsado = hardware.boton_presionado()
    gesto_resuelto = hardware.detectar_gesto_boton_control()
    start_requested = (gesto_resuelto == hardware.GESTO_PAUSA)
    
    # Registrar actividad del usuario para prolongar el tiempo antes de entrar a hibernar
    if ((estado_actual != ESTADO_STANDBY and not pausado) or 
            botón_pulsado or 
            (gesto_resuelto != hardware.GESTO_NINGUNO)):
        registrar_actividad()
    
    # GESTO MANTENER: Reset total al modo de espera (Standby)
    if gesto_resuelto == hardware.GESTO_RESET_IDLE:
        if estado_actual != ESTADO_STANDBY:
            fase_nombre = obtener_nombre_fase(estado_actual)
            duracion_parcial_s = (tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)) // 1000
            
            # Si estaba pausado, reportar la pausa acumulada antes de cancelar
            if pausado and inicio_pausa_ms > 0:
                duracion_pausa_s = time.ticks_diff(ahora, inicio_pausa_ms) // 1000
                total_s = config.tiempo_focus_s if estado_actual == ESTADO_FOCUS else (config.tiempo_descanso_corto_s if estado_actual == ESTADO_DESCANSO_CORTO else config.tiempo_descanso_largo_s)
                pct = min(100.0, (tiempo_acumulado_ms // 1000) / total_s * 100.0) if total_s > 0 else 0.0
                reportar_pausa(fase_nombre, tiempo_acumulado_ms // 1000, pct, duracion_pausa_s)
                
            reportar_ciclo(fase_nombre, "CANCELADO", duracion_parcial_s)
            
            audio.play_reset_idle()
            estado_actual = ESTADO_STANDBY
            pausado = False
            tiempo_acumulado_ms = 0
            ciclos_focus_consecutivos = 0
            ultimo_titilo = ahora
            print("[POMODORO] Reset total. Regreso a STANDBY. Ciclos de descanso reiniciados.")
            config.print_configuracion_actual()
        return

    # GESTOS EN TIEMPO DE FASE: Pausa y Reset local de fase
    if estado_actual != ESTADO_STANDBY and estado_actual != ESTADO_ALERTA_TITILANDO:
        # Triple clic -> Avance Forzado de Fase
        if gesto_resuelto == hardware.GESTO_AVANCE_FORZADO:
            fase_nombre = obtener_nombre_fase(estado_actual)
            duracion_parcial_s = (tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)) // 1000
            
            # Si estaba pausado, reportar la pausa antes de avanzar
            if pausado and inicio_pausa_ms > 0:
                duracion_pausa_s = time.ticks_diff(ahora, inicio_pausa_ms) // 1000
                total_s = config.tiempo_focus_s if estado_actual == ESTADO_FOCUS else (config.tiempo_descanso_corto_s if estado_actual == ESTADO_DESCANSO_CORTO else config.tiempo_descanso_largo_s)
                pct = min(100.0, (tiempo_acumulado_ms // 1000) / total_s * 100.0) if total_s > 0 else 0.0
                reportar_pausa(fase_nombre, tiempo_acumulado_ms // 1000, pct, duracion_pausa_s)
                inicio_pausa_ms = 0
            
            hardware.sonar_buzzer(0, False)
            hardware.set_color_pwm(0, 0, 0)
            
            if estado_actual == ESTADO_FOCUS:
                ciclos_focus_consecutivos += 1
                print("[POMODORO] Avance Forzado de FOCUS ({}s)".format(duracion_parcial_s))
                
                enviar_reporte_flask("focus", ciclos_focus_consecutivos, duracion_parcial_s, forzado=1)
                reportar_ciclo("FOCUS", "FORZADO", duracion_parcial_s)
                
                # Determinar si corresponde ir a descanso largo o corto
                es_descanso_largo = (
                    config.descanso_largo_activo and 
                    (ciclos_focus_consecutivos % max(2, config.ciclos_para_descanso_largo) == 0)
                )
                
                if es_descanso_largo:
                    estado_actual = ESTADO_DESCANSO_LARGO
                    print("[POMODORO] Inicio DESCANSO LARGO directo (LED Verde, {}s).".format(config.tiempo_descanso_largo_s))
                    reportar_ciclo("DESCANSO_LARGO", "INICIADO", 0)
                else:
                    estado_actual = ESTADO_DESCANSO_CORTO
                    print("[POMODORO] Inicio DESCANSO CORTO directo (LED Azul, {}s).".format(config.tiempo_descanso_corto_s))
                    reportar_ciclo("DESCANSO_CORTO", "INICIADO", 0)
            else:
                print("[POMODORO] Avance Forzado de descanso {} ({}s)".format(fase_nombre, duracion_parcial_s))
                
                enviar_reporte_flask("descanso_largo" if estado_actual == ESTADO_DESCANSO_LARGO else "descanso_corto", ciclos_focus_consecutivos, duracion_parcial_s, forzado=1)
                reportar_ciclo(fase_nombre, "FORZADO", duracion_parcial_s)
                
                estado_actual = ESTADO_FOCUS
                print("[POMODORO] Inicio Sesión FOCUS directo ({}s).".format(config.tiempo_focus_s))
                reportar_ciclo("FOCUS", "INICIADO", 0)
                
            cronometro = ahora
            tiempo_acumulado_ms = 0
            pausado = False
            
            audio.play_start_warm()
            time.sleep_ms(config.DEBOUNCE_BOTON_MS)
            return

        # Doble clic -> Reiniciar temporizador de fase actual a 0s
        if gesto_resuelto == hardware.GESTO_RESET_FASE:
            fase_nombre = obtener_nombre_fase(estado_actual)
            duracion_parcial_s = (tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)) // 1000
            
            # Si estaba pausado, reportar la pausa antes de cancelar
            if pausado and inicio_pausa_ms > 0:
                duracion_pausa_s = time.ticks_diff(ahora, inicio_pausa_ms) // 1000
                total_s = config.tiempo_focus_s if estado_actual == ESTADO_FOCUS else (config.tiempo_descanso_corto_s if estado_actual == ESTADO_DESCANSO_CORTO else config.tiempo_descanso_largo_s)
                pct = min(100.0, (tiempo_acumulado_ms // 1000) / total_s * 100.0) if total_s > 0 else 0.0
                reportar_pausa(fase_nombre, tiempo_acumulado_ms // 1000, pct, duracion_pausa_s)
            
            reportar_ciclo(fase_nombre, "CANCELADO", duracion_parcial_s)
            
            cronometro = ahora
            tiempo_acumulado_ms = 0
            pausado = False
            
            reportar_ciclo(fase_nombre, "INICIADO", 0)
            
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
                
                # Iniciar tracking de pausa
                inicio_pausa_ms = ahora
            else:
                cronometro = ahora
                print("[POMODORO] Temporizador REANUDADO.")
                audio.play_resume()
                
                # Calcular y reportar pausa
                if inicio_pausa_ms > 0:
                    duracion_pausa_s = time.ticks_diff(ahora, inicio_pausa_ms) // 1000
                    fase_nombre = obtener_nombre_fase(estado_actual)
                    
                    if estado_actual == ESTADO_FOCUS:
                        total_s = config.tiempo_focus_s
                    elif estado_actual == ESTADO_DESCANSO_CORTO:
                        total_s = config.tiempo_descanso_corto_s
                    else:
                        total_s = config.tiempo_descanso_largo_s
                        
                    tiempo_transcurrido_s = tiempo_acumulado_ms // 1000
                    pct = min(100.0, (tiempo_transcurrido_s / total_s) * 100.0) if total_s > 0 else 0.0
                    
                    reportar_pausa(fase_nombre, tiempo_transcurrido_s, pct, duracion_pausa_s)
                    inicio_pausa_ms = 0
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
            
            # Preparar pin para disparar el despertar lógico por flanco descendente (0)
            import machine
            import esp32
            
            wake_pin = machine.Pin(config.PIN_BTN, machine.Pin.IN, machine.Pin.PULL_UP)
            esp32.wake_on_ext0(pin=wake_pin, level=0)
            
            # Entrar en deepsleep (se reiniciará el programa al despertar)
            machine.deepsleep()


