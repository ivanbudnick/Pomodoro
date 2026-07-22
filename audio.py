import time
import hardware

# --- DICCIONARIO DE NOTAS Y SUS FRECUENCIAS (Como referencia) ---
# Do4 = 261, Re4 = 294, Mi4 = 330, Fa4 = 349, Sol4 = 392, La4 = 440, Si4 = 494
# Do5 = 523, Re5 = 587, Mi5 = 659, Fa5 = 698, Sol5 = 784, La5 = 880, Si5 = 988
# Do6 = 1046

def _tocar_nota(frecuencia, duracion_ms, pausa_ms=10):
    """Función helper interna para reproducir una nota en el buzzer con un pequeño silencio posterior"""
    hardware.sonar_buzzer(frecuencia, True)
    time.sleep_ms(duracion_ms)
    hardware.sonar_buzzer(0, False)
    if pausa_ms > 0:
        time.sleep_ms(pausa_ms)

def play_start_cold():
    """Sonido al iniciar Focus desde Standby (Cold Start): Bitono ascendente y motivador"""
    _tocar_nota(523, 70)  # Do5
    _tocar_nota(659, 80, 0)  # Mi5

def play_start_warm():
    """Sonido al iniciar Focus desde Alerta (Siguiente ciclo): Dos pitidos rápidos de avance"""
    _tocar_nota(880, 50, 40)  # La5
    _tocar_nota(880, 50, 0)  # La5

def play_pause():
    """Sonido al Pausar: Descenso corto y apagado de detención"""
    _tocar_nota(294, 60, 15)  # Re4
    _tocar_nota(261, 60, 0)  # Do4

def play_resume():
    """Sonido al Reanudar: Pitido agudo rápido y optimista"""
    _tocar_nota(1046, 50, 0)  # Do6

def play_done_focus():
    """Sonido al terminar Focus (Fin de sesión): Progresión armónica de 4 notas muy satisfactoria"""
    _tocar_nota(523, 60, 15)   # Do5
    _tocar_nota(659, 60, 15)   # Mi5
    _tocar_nota(784, 60, 15)   # Sol5
    _tocar_nota(1046, 120, 0)  # Do6 (Cierre triunfal)

def play_done_break():
    """Sonido al terminar el Descanso (Fin de descanso): Subida suave y amigable de 3 notas"""
    _tocar_nota(698, 50)  # Fa5
    _tocar_nota(784, 50)  # Sol5
    _tocar_nota(880, 80, 0)  # La5

def play_alert_pip():
    """Sonido en Alerta (Mientras parpadea): Un 'pip' muy discreto e intermitente"""
    _tocar_nota(587, 30, 0)  # Re5

def play_reset_phase():
    """Sonido al reiniciar la fase actual (Doble clic): Tono de rebote de reinicio"""
    _tocar_nota(659, 40, 20)  # Mi5
    _tocar_nota(523, 40, 20)  # Do5
    _tocar_nota(659, 60, 0)  # Mi5

def play_reset_idle():
    """Sonido al volver a Standby (Mantener presionado): Melodía descendente lenta de despedida"""
    _tocar_nota(392, 100, 20)  # Sol4
    _tocar_nota(330, 100, 20)  # Mi4
    _tocar_nota(261, 150, 0)  # Do4

def play_sleep_in():
    """Sonido al entrar en Deep Sleep por inactividad: Apagado descendente y profundo"""
    _tocar_nota(659, 150, 30)  # Mi5
    _tocar_nota(523, 150, 30)  # Do5
    _tocar_nota(392, 250, 0)  # Sol4

def play_sleep_out():
    """Sonido al despertar de Deep Sleep: Acorde brillante y progresivo ascendente de encendido"""
    _tocar_nota(261, 70)  # Do4
    _tocar_nota(392, 70)  # Sol4
    _tocar_nota(523, 70)  # Do5
    _tocar_nota(659, 120, 0)  # Mi5
