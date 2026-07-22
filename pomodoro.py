import time
import config
import hardware
import audio

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
cronometro = time.ticks_ms()
ultimo_titilo = time.ticks_ms()
estado_luz_titilo = False
ciclos_focus_consecutivos = 0
ultimo_evento_ms = time.ticks_ms()  # Marca de tiempo de la última actividad o interacción
color_alerta_actual = "azul"        # Color de alerta contextual (azul tras descanso corto, verde tras largo)

# Variables de control de pausa
pausado = False
tiempo_acumulado_ms = 0

def enviar_reporte_flask(tipo_sesion, ciclo_num, duracion_s):
    """Envía un reporte HTTP POST a la PC usando urequests al finalizar una sesión"""
    try:
        import urequests
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
    except Exception as e:
        print("[FLASK REPORT WARNING] No se pudo enviar el reporte a la PC:", e)

def obtener_dict_estado():
    """Retorna un diccionario completo de estado para la API del servidor web y dashboard"""
    ahora = time.ticks_ms()
    nombre = NOMBRES_ESTADO.get(estado_actual, "DESCONOCIDO")
    
    # Calcular segundos restantes contemplando si está pausado
    remaining_s = 0
    if estado_actual == ESTADO_FOCUS:
        duracion_ms = config.tiempo_focus_s * 1000
        transcurrido = tiempo_acumulado_ms + (time.ticks_diff(ahora, cronometro) if not pausado else 0)
        remaining_s = max(0, int((duracion_ms - transcurrido) / 1000))
    elif estado_actual == ESTADO_DESCANSO_CORTO:
        duracion_ms = config.tiempo_descanso_corto_s * 1000
        transcurrido = tiempo_acumulado_ms + (time.ticks_diff(ahora, cronometro) if not pausado else 0)
        remaining_s = max(0, int((duracion_ms - transcurrido) / 1000))
    elif estado_actual == ESTADO_DESCANSO_LARGO:
        duracion_ms = config.tiempo_descanso_largo_s * 1000
        transcurrido = tiempo_acumulado_ms + (time.ticks_diff(ahora, cronometro) if not pausado else 0)
        remaining_s = max(0, int((duracion_ms - transcurrido) / 1000))
        
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

def ejecutar_pomodoro_step():
    """Ejecuta un tick no bloqueante de la máquina de estados del Pomodoro Pro con Pausa y Resets"""
    global estado_actual, cronometro, ultimo_titilo, estado_luz_titilo, ciclos_focus_consecutivos, pausado, tiempo_acumulado_ms, color_alerta_actual
    
    ahora = time.ticks_ms()
    botón_pulsado = hardware.boton_presionado()
    gesto = hardware.detectar_gesto_boton_control()
    
    # Registrar actividad ante interacciones físicas o estados activos corriendo
    if (estado_actual != ESTADO_STANDBY and not pausado) or botón_pulsado or (gesto != hardware.GESTO_NINGUNO):
        registrar_actividad()
    
    # 1. PROCESAR GESTO: RESET IDLE (Mantener presionado 2 segundos) -> vuelve a Standby
    # 1. PROCESAR GESTO: RESET IDLE (Mantener presionado 2 segundos) -> vuelve a Standby
    if gesto == hardware.GESTO_RESET_IDLE:
        audio.play_reset_idle()
        estado_actual = ESTADO_STANDBY
        pausado = False
        tiempo_acumulado_ms = 0
        ultimo_titilo = ahora
        print("[POMODORO] Reset total. Regreso a STANDBY.")
        return

    # 2. PROCESAR GESTOS SI NO ESTAMOS EN STANDBY
    if estado_actual != ESTADO_STANDBY:
        # Doble clic -> Resetear fase actual a 0s
        if gesto == hardware.GESTO_RESET_FASE:
            cronometro = ahora
            tiempo_acumulado_ms = 0
            pausado = False
            audio.play_reset_phase()
            print("[POMODORO] Fase actual reseteada a 0s. (No cuenta en BD)")
            return

        # Clic simple -> Pausar / Reanudar
        if gesto == hardware.GESTO_PAUSA:
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

    # 3. SI EL TEMPORIZADOR ESTÁ PAUSADO: Parpadear luz en color de fase activa con su intensidad congelada
    if pausado and estado_actual != ESTADO_STANDBY and estado_actual != ESTADO_ALERTA_TITILANDO:
        hardware.sonar_buzzer(0, False)
        if time.ticks_diff(ahora, ultimo_titilo) >= 500:
            estado_luz_titilo = not estado_luz_titilo
            if estado_luz_titilo:
                # Determinar duración total para calcular la intensidad actual
                duracion_ms = 1
                if estado_actual == ESTADO_FOCUS:
                    duracion_ms = config.tiempo_focus_s * 1000
                elif estado_actual == ESTADO_DESCANSO_CORTO:
                    duracion_ms = config.tiempo_descanso_corto_s * 1000
                elif estado_actual == ESTADO_DESCANSO_LARGO:
                    duracion_ms = config.tiempo_descanso_largo_s * 1000
                
                # Calcular la intensidad correspondiente al instante pausado
                intensidad = hardware.calcular_intensidad_progresiva(tiempo_acumulado_ms, duracion_ms)
                
                if estado_actual == ESTADO_FOCUS:
                    hardware.set_color_pwm(intensidad, 0, 0) # Rojo
                elif estado_actual == ESTADO_DESCANSO_CORTO:
                    hardware.set_color_pwm(0, 0, intensidad) # Azul
                elif estado_actual == ESTADO_DESCANSO_LARGO:
                    hardware.set_color_pwm(0, intensidad, 0) # Verde
            else:
                hardware.set_color_pwm(0, 0, 0)
            ultimo_titilo = ahora
        return


    # 4. MÁQUINA DE ESTADOS PRINCIPAL
    # ESTADO 0: STANDBY (Amarillo parpadeando)
    if estado_actual == ESTADO_STANDBY:
        hardware.sonar_buzzer(0, False)
        
        if time.ticks_diff(ahora, ultimo_titilo) >= config.INTERVALO_TITILO_STANDBY_MS:
            estado_luz_titilo = not estado_luz_titilo
            if estado_luz_titilo:
                hardware.set_color_pwm(config.DUTY_MAX, config.DUTY_MAX, 0) # Amarillo ON
            else:
                hardware.set_color_pwm(0, 0, 0)
            ultimo_titilo = ahora
            
        if botón_pulsado:
            cronometro = ahora
            tiempo_acumulado_ms = 0
            pausado = False
            estado_actual = ESTADO_FOCUS
            print("[POMODORO] Inicio Sesión FOCUS ({}s).".format(config.tiempo_focus_s))
            audio.play_start_cold()
            time.sleep_ms(config.DEBOUNCE_BOTON_MS)

    # ESTADO 1: FOCUS (Luz roja progresiva exponencial)
    elif estado_actual == ESTADO_FOCUS:
        hardware.sonar_buzzer(0, False)
        
        transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
        duracion_ms = config.tiempo_focus_s * 1000
        intensidad_rojo = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
        
        hardware.set_color_pwm(intensidad_rojo, 0, 0)
        
        if transcurrido >= duracion_ms:
            ciclos_focus_consecutivos += 1
            print("[POMODORO] ¡Sesión FOCUS #{} Completada! ({}s)".format(ciclos_focus_consecutivos, config.tiempo_focus_s))
            
            # Sonido de cambio de estado
            audio.play_done_focus()
            
            # Guardar en Base de Datos de la PC (Focus completado con éxito)
            enviar_reporte_flask("focus", ciclos_focus_consecutivos, config.tiempo_focus_s)
            
            cronometro = ahora
            tiempo_acumulado_ms = 0
            
            # Determinar si corresponde descanso largo o corto
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

    # ESTADO 2: DESCANSO CORTO (Luz azul progresiva exponencial)
    elif estado_actual == ESTADO_DESCANSO_CORTO:
        transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
        duracion_ms = config.tiempo_descanso_corto_s * 1000
        intensidad_azul = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
        
        hardware.set_color_pwm(0, 0, intensidad_azul)
        
        if transcurrido >= duracion_ms:
            hardware.set_color_pwm(0, 0, 0)
            audio.play_done_break()
            
            # Reportar descanso corto completado a la PC
            enviar_reporte_flask("descanso_corto", ciclos_focus_consecutivos, config.tiempo_descanso_corto_s)
            
            cronometro = ahora
            tiempo_acumulado_ms = 0
            ultimo_titilo = time.ticks_ms()
            estado_luz_titilo = True
            color_alerta_actual = "azul"
            estado_actual = ESTADO_ALERTA_TITILANDO
            print("[POMODORO] Fin Descanso Corto. Estado: Alerta (Azul).")

    # ESTADO 3: DESCANSO LARGO (Luz verde progresiva exponencial)
    elif estado_actual == ESTADO_DESCANSO_LARGO:
        transcurrido = tiempo_acumulado_ms + time.ticks_diff(ahora, cronometro)
        duracion_ms = config.tiempo_descanso_largo_s * 1000
        intensidad_verde = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
        
        hardware.set_color_pwm(0, intensidad_verde, 0)
        
        if transcurrido >= duracion_ms:
            hardware.set_color_pwm(0, 0, 0)
            audio.play_done_break()
            
            # Reportar descanso largo completado a la PC
            enviar_reporte_flask("descanso_largo", ciclos_focus_consecutivos, config.tiempo_descanso_largo_s)
            
            cronometro = ahora
            tiempo_acumulado_ms = 0
            ultimo_titilo = time.ticks_ms()
            estado_luz_titilo = True
            color_alerta_actual = "verde"
            estado_actual = ESTADO_ALERTA_TITILANDO
            print("[POMODORO] Fin Descanso Largo. Estado: Alerta (Verde).")

    # ESTADO 4: ALERTA (Parpadeo azul + pitido sutil)
    elif estado_actual == ESTADO_ALERTA_TITILANDO:
        if time.ticks_diff(ahora, ultimo_titilo) >= config.INTERVALO_ALERTA_MS:
            estado_luz_titilo = not estado_luz_titilo
            if estado_luz_titilo:
                # Color de alerta contextual basado en el tipo de descanso que finalizó
                if color_alerta_actual == "verde":
                    hardware.set_color_pwm(0, config.DUTY_MAX, 0) # Verde ON
                else:
                    hardware.set_color_pwm(0, 0, config.DUTY_MAX) # Azul ON
                audio.play_alert_pip()
            else:
                hardware.set_color_pwm(0, 0, 0) # Apagado
                hardware.sonar_buzzer(0, False)
            ultimo_titilo = ahora
            
        if botón_pulsado:
            hardware.sonar_buzzer(0, False)
            cronometro = ahora
            tiempo_acumulado_ms = 0
            pausado = False
            estado_actual = ESTADO_FOCUS
            print("[POMODORO] Reinicio. Inicio Sesión FOCUS ({}s).".format(config.tiempo_focus_s))
            audio.play_start_warm()
            time.sleep_ms(config.DEBOUNCE_BOTON_MS)


def registrar_actividad():
    """Actualiza la marca de tiempo de la última interacción detectada"""
    global ultimo_evento_ms
    ultimo_evento_ms = time.ticks_ms()


def verificar_y_ejecutar_sleep():
    """Evalúa si el dispositivo ha estado inactivo en STANDBY y ejecuta Deep Sleep si corresponde"""
    global estado_actual, ultimo_evento_ms
    if estado_actual == ESTADO_STANDBY:
        ahora = time.ticks_ms()
        transcurrido_ms = time.ticks_diff(ahora, ultimo_evento_ms)
        if transcurrido_ms >= config.TIEMPO_INACTIVIDAD_SLEEP_MS:
            print("[SLEEP] Pomodoro inactivo por {}s. Entrando en Deep Sleep...".format(transcurrido_ms // 1000))
            
            # Melodía de apagado
            audio.play_sleep_in()
            
            # Apagar el LED RGB completamente
            hardware.set_color_pwm(0, 0, 0)
            
            # Configurar el botón de inicio (GPIO 25) para despertar
            import machine
            import esp32
            
            wake_pin = machine.Pin(config.PIN_BTN, machine.Pin.IN, machine.Pin.PULL_UP)
            esp32.wake_on_ext0(pin=wake_pin, level=0)
            
            # Dormir indefinidamente
            machine.deepsleep()
