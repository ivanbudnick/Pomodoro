import time
import config
import hardware

# --- ESTADOS DEL SISTEMA POMODORO ---
ESTADO_AMARILLO_TITILANDO = 0
ESTADO_ROJO               = 1
ESTADO_AZUL               = 2
ESTADO_ALERTA_TITILANDO   = 3

NOMBRES_ESTADO = {
    ESTADO_AMARILLO_TITILANDO: "AMARILLO",
    ESTADO_ROJO: "ROJO",
    ESTADO_AZUL: "AZUL",
    ESTADO_ALERTA_TITILANDO: "ALERTA"
}

# --- VARIABLES DE ESTADO GLOBALES ---
estado_actual = ESTADO_AMARILLO_TITILANDO
cronometro = time.ticks_ms()
ultimo_titilo = time.ticks_ms()
estado_luz_titilo = False
ciclos_rojos_completados = 0

def enviar_reporte_flask(ciclo_num, duracion_s):
    """Envía un reporte HTTP POST a la PC usando urequests al completar la fase roja"""
    try:
        import urequests
        payload = {
            "dispositivo": "ESP32_Pomodoro",
            "evento": "ciclo_rojo_completado",
            "ciclo_num": ciclo_num,
            "duracion_s": duracion_s
        }
        res = urequests.post(config.FLASK_SERVER_URL, json=payload)
        print("[FLASK REPORT] Evento enviado a la PC (192.168.0.125). Estado HTTP:", res.status_code)
        res.close()
    except Exception as e:
        print("[FLASK REPORT WARNING] No se pudo enviar el reporte a la PC:", e)

def obtener_dict_estado():
    """Retorna un diccionario con el estado actual y segundos restantes para la API web"""
    ahora = time.ticks_ms()
    nombre = NOMBRES_ESTADO.get(estado_actual, "DESCONOCIDO")
    remaining_s = 0
    
    if estado_actual == ESTADO_ROJO:
        transcurrido = time.ticks_diff(ahora, cronometro)
        duracion_ms = config.tiempo_rojo_s * 1000
        remaining_s = max(0, int((duracion_ms - transcurrido) / 1000))
    elif estado_actual == ESTADO_AZUL:
        transcurrido = time.ticks_diff(ahora, cronometro)
        duracion_ms = config.tiempo_azul_s * 1000
        remaining_s = max(0, int((duracion_ms - transcurrido) / 1000))
        
    return {
        "estado": estado_actual,
        "estado_nombre": nombre,
        "remaining_s": remaining_s,
        "tiempo_rojo": config.tiempo_rojo_s,
        "tiempo_azul": config.tiempo_azul_s,
        "ciclos_completados": ciclos_rojos_completados
    }

def ejecutar_pomodoro_step():
    """Ejecuta un tick no bloqueante de la máquina de estados del Pomodoro"""
    global estado_actual, cronometro, ultimo_titilo, estado_luz_titilo, ciclos_rojos_completados
    
    ahora = time.ticks_ms()
    botón_pulsado = hardware.boton_presionado()
    
    # ESTADO 0: Amarillo titilando al arrancar (Espera)
    if estado_actual == ESTADO_AMARILLO_TITILANDO:
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
            estado_actual = ESTADO_ROJO
            print("[POMODORO] Inicio. Estado: Rojo progresivo ({}s).".format(config.tiempo_rojo_s))
            hardware.reproducir_pitidos(config.FREQ_BUZZER_INICIO, repeticiones=1, duracion_ms=70)
            time.sleep_ms(config.DEBOUNCE_BOTON_MS)

    # ESTADO 1: Luz roja progresiva por tiempo_rojo_s
    elif estado_actual == ESTADO_ROJO:
        hardware.sonar_buzzer(0, False)
        
        transcurrido = time.ticks_diff(ahora, cronometro)
        duracion_ms = config.tiempo_rojo_s * 1000
        intensidad_rojo = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
        
        hardware.set_color_pwm(intensidad_rojo, 0, 0)
        
        if transcurrido >= duracion_ms:
            ciclos_rojos_completados += 1
            print("[POMODORO] ¡Ciclo Rojo #{} Completado ({}s)!".format(ciclos_rojos_completados, config.tiempo_rojo_s))
            
            # Sonido de cambio de estado
            hardware.reproducir_pitidos(config.FREQ_BUZZER_CAMBIO_ESTADO, repeticiones=2, duracion_ms=70, pausa_ms=50)
            
            # Enviar reporte a la BD en el servidor Flask de la PC
            enviar_reporte_flask(ciclos_rojos_completados, config.tiempo_rojo_s)
            
            cronometro = ahora
            estado_actual = ESTADO_AZUL
            print("[POMODORO] Estado: Azul progresivo ({}s).".format(config.tiempo_azul_s))

    # ESTADO 2: Luz azul progresiva por tiempo_azul_s
    elif estado_actual == ESTADO_AZUL:
        
        transcurrido = time.ticks_diff(ahora, cronometro)
        duracion_ms = config.tiempo_azul_s * 1000
        intensidad_azul = hardware.calcular_intensidad_progresiva(transcurrido, duracion_ms)
        
        hardware.set_color_pwm(0, 0, intensidad_azul)
        
        if transcurrido >= duracion_ms:
            hardware.set_color_pwm(0, 0, 0)
            hardware.reproducir_pitidos(config.FREQ_BUZZER_TRANSICION, repeticiones=2, duracion_ms=70, pausa_ms=50)
            
            ultimo_titilo = time.ticks_ms()
            estado_luz_titilo = True
            estado_actual = ESTADO_ALERTA_TITILANDO
            print("[POMODORO] Fin Azul ({}s). Estado: Alerta titilando.".format(config.tiempo_azul_s))

    # ESTADO 3: Alerta con parpadeo y toque sutil de sonido
    elif estado_actual == ESTADO_ALERTA_TITILANDO:
        if time.ticks_diff(ahora, ultimo_titilo) >= config.INTERVALO_ALERTA_MS:
            estado_luz_titilo = not estado_luz_titilo
            if estado_luz_titilo:
                hardware.set_color_pwm(0, 0, config.DUTY_MAX) # Azul ON
                hardware.sonar_buzzer(config.FREQ_BUZZER_ALERTA, True)
                time.sleep_ms(50)
                hardware.sonar_buzzer(0, False)
            else:
                hardware.set_color_pwm(0, 0, 0) # Apagado
                hardware.sonar_buzzer(0, False)
            ultimo_titilo = ahora
            
        if botón_pulsado:
            hardware.sonar_buzzer(0, False)
            cronometro = ahora
            estado_actual = ESTADO_ROJO
            print("[POMODORO] Reinicio. Estado: Rojo progresivo ({}s).".format(config.tiempo_rojo_s))
            hardware.reproducir_pitidos(config.FREQ_BUZZER_INICIO, repeticiones=1, duracion_ms=70)
            time.sleep_ms(config.DEBOUNCE_BOTON_MS)
