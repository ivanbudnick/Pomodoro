# ==============================================================================
# MÓDULO DE SEÑALES ACÚSTICAS (AUDIO Y MELODÍAS)
# ==============================================================================
# Este módulo se encarga de producir el feedback auditivo para cada uno de los
# eventos del Pomodoro Pro, utilizando el zumbador (buzzer) piezoeléctrico pasivo.
#
# Generación de Notas: Se utiliza modulación de ancho de pulso (PWM). Al cambiar
# la frecuencia del pin PWM, el diafragma del zumbador vibra a esa velocidad en Hz,
# produciendo notas musicales del sistema.
#
# Técnica de Articulación (Silencios): Para evitar que las notas de una melodía se
# fusionen en un único zumbido continuo, la función '_tocar_nota' impone siempre
# un micro-silencio (pausa_ms) al desactivar el duty cycle del pin antes de tocar
# la siguiente nota.

import time
import hardware

# --- REFERENCIA DE FRECUENCIAS DE NOTAS MUSICALES (Hz) ---
# Octava 4 (Tonos medios): Do4=261, Re4=294, Mi4=330, Fa4=349, Sol4=392, La4=440, Si4=494
# Octava 5 (Tonos agudos): Do5=523, Re5=587, Mi5=659, Fa5=698, Sol5=784, La5=880, Si5=988
# Octava 6 (Muy agudo):    Do6=1046

def _tocar_nota(frecuencia, duracion_ms, pausa_ms=10):
    """
    Produce un tono singular en el zumbador.
    - frecuencia: Tono en Hz de la nota.
    - duracion_ms: Tiempo en milisegundos que vibra el zumbador.
    - pausa_ms: Silencio posterior obligatorio para separar notas consecutivas.
    """
    hardware.sonar_buzzer(frecuencia, True)
    time.sleep_ms(duracion_ms)
    hardware.sonar_buzzer(0, False)
    if pausa_ms > 0:
        time.sleep_ms(pausa_ms)

def play_start_cold():
    """
    Melodía de Inicio en Frío (Cold Start): Do5 -> Mi5.
    Se ejecuta al iniciar un ciclo Focus desde el estado inactivo (Standby).
    Es un tono bi-nota ascendente corto y estimulante para marcar el inicio del trabajo.
    """
    _tocar_nota(523, 70)  # Do5
    _tocar_nota(659, 80, 0)  # Mi5

def play_start_warm():
    """
    Melodía de Inicio en Caliente (Warm Start): La5 (50ms) -> Silencio -> La5 (50ms).
    Se ejecuta cuando el usuario presiona el botón para avanzar tras finalizar una alerta.
    Son dos pitidos idénticos y sumamente rápidos que indican continuación del trabajo.
    """
    _tocar_nota(880, 50, 40)  # La5
    _tocar_nota(880, 50, 0)  # La5

def play_pause():
    """
    Melodía de Pausa: Re4 -> Do4.
    Es una progresión descendente corta de baja frecuencia que da una sensación
    de apagado temporal o detención de actividad.
    """
    _tocar_nota(294, 60, 15)  # Re4
    _tocar_nota(261, 60, 0)  # Do4

def play_resume():
    """
    Melodía de Reanudación: Do6.
    Un único pitido extremadamente agudo y breve (50ms) para notificar de
    manera sutil y optimista que el cronómetro ha vuelto a correr.
    """
    _tocar_nota(1046, 50, 0)  # Do6

def play_done_focus():
    """
    Melodía de Fin de Enfoque (Focus Completado): Do5 -> Mi5 -> Sol5 -> Do6.
    Es un acorde arpegiado ascendente mayor de 4 notas que simula un cierre
    exitoso o 'logro', brindando una recompensa auditiva placentera al usuario.
    """
    _tocar_nota(523, 60, 15)   # Do5
    _tocar_nota(659, 60, 15)   # Mi5
    _tocar_nota(784, 60, 15)   # Sol5
    _tocar_nota(1046, 120, 0)  # Do6 (Acorde triunfal prolongado)

def play_done_break():
    """
    Melodía de Fin de Descanso: Fa5 -> Sol5 -> La5.
    Una escala ascendente alegre de tres notas en octava alta que informa amablemente
    al usuario que el tiempo de descanso ha expirado y debe retornar a sus tareas.
    """
    _tocar_nota(698, 50)  # Fa5
    _tocar_nota(784, 50)  # Sol5
    _tocar_nota(880, 80, 0)  # La5

def play_alert_pip():
    """
    Sonido en Estado Alerta: Re5.
    Un 'pip' aislado, discreto y muy corto (30ms). Se repite de forma síncrona
    con el parpadeo del LED de alerta para capturar la atención sin ser irritante.
    """
    _tocar_nota(587, 30, 0)  # Re5

def play_reset_phase():
    """
    Melodía de Reset de Fase (Doble Clic): Mi5 -> Do5 -> Mi5.
    Produce un sonido rápido tipo 'rebote' que confirma que el tiempo de la
    fase actual (Focus o Descanso) se ha restablecido a cero.
    """
    _tocar_nota(659, 40, 20)  # Mi5
    _tocar_nota(523, 40, 20)  # Do5
    _tocar_nota(659, 60, 0)  # Mi5

def play_reset_idle():
    """
    Melodía de Retorno a Standby (Pulsación Larga): Sol4 -> Mi4 -> Do4.
    Es una melodía descendente y pausada que le indica sonoramente al usuario
    que todo el ciclo actual y las estadísticas del dispositivo se han borrado.
    """
    _tocar_nota(392, 100, 20)  # Sol4
    _tocar_nota(330, 100, 20)  # Mi4
    _tocar_nota(261, 150, 0)  # Do4

def play_sleep_in():
    """
    Melodía de Entrada a Deep Sleep (Apagado): Mi5 -> Do5 -> Sol4.
    Progresión descendente que cae en baja frecuencia, transmitiendo
    la idea de apagado o transición al sueño profundo del microcontrolador.
    """
    _tocar_nota(659, 150, 30)  # Mi5
    _tocar_nota(523, 150, 30)  # Do5
    _tocar_nota(392, 250, 0)  # Sol4

def play_sleep_out():
    """
    Melodía de Salida de Deep Sleep (Despertar): Do4 -> Sol4 -> Do5 -> Mi5.
    Un arpegio mayor ascendente brillante que se reproduce inmediatamente cuando
    la ESP32 despierta del bajo consumo para indicar que está activa e inicia Focus.
    """
    _tocar_nota(261, 70)  # Do4
    _tocar_nota(392, 70)  # Sol4
    _tocar_nota(523, 70)  # Do5
    _tocar_nota(659, 120, 0)  # Mi5
