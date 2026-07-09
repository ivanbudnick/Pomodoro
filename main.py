import machine
import time

# --- PIN CONFIGURATION ---
BUTTON_PIN = 12   # Pin for the push button
RED_LED_PIN = 14    # Pin for the Red LED
BLUE_LED_PIN = 27   # Pin for the Blue LED

# Component initialization
# Use PULL_UP for the button (assumes button connects to GND when pressed)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
red_led = machine.Pin(RED_LED_PIN, machine.Pin.OUT)
blue_led = machine.Pin(BLUE_LED_PIN, machine.Pin.OUT)

# --- STATE VARIABLES ---
# Initially, the system is idle.
is_idle = True
red_start_time = 0

# Ensure everything starts turned off
red_led.value(0)
blue_led.value(0)

print("System started. Waiting for button press...")

# --- MAIN LOOP ---
while True:
    # Read button (with PULL_UP, 0 means pressed)
    button_pressed = (button.value() == 0)
    
    if is_idle:
        if button_pressed:
            print("Button pressed: Turning on Red LED for 10 seconds.")
            red_led.value(1)
            blue_led.value(0)
            red_start_time = time.ticks_ms()  # Save the current millisecond
            is_idle = False
            time.sleep(0.2)  # Avoid repeated instantaneous readings
            
    else:
        # If not idle, determine the state based on the elapsed time
        elapsed_time = time.ticks_diff(time.ticks_ms(), red_start_time)
        
        if elapsed_time < 10000:
            # We are in the Red LED phase. Button presses are ignored here.
            pass
        else:
            # We are in the Blue LED phase.
            if blue_led.value() == 0:
                print("10 seconds passed: Switching to Blue LED.")
                red_led.value(0)
                blue_led.value(1)
                
            if button_pressed:
                print("Button pressed in Blue: Restarting cycle to Red LED.")
                blue_led.value(0)
                red_led.value(1)
                red_start_time = time.ticks_ms()  # Restart the timer
                time.sleep(0.2)  # Avoid repeated instantaneous readings
                
    # Small pause to avoid overloading the simulation processor
    time.sleep(0.01)
