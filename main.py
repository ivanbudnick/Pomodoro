import machine
import time
import network
import urequests

# --- WIFI & SERVER CONFIGURATION ---
WIFI_SSID = "Wokwi-GUEST"  # Default SSID for Wokwi simulation
WIFI_PASSWORD = ""         # Wokwi-GUEST has no password
# Replace this URL with your localtunnel or ngrok public URL
SERVER_URL = "http://tired-emus-hammer.loca.lt" 

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
is_idle = True
red_start_time = 0
red_duration_s = 10  # Default duration in seconds (synced from server)

# Track last reported state to avoid redundant HTTP requests
last_reported_idle = None
last_reported_remaining = None
last_reported_led = None

# Network error rate limiting
server_offline = False
last_offline_time = 0

# Ensure everything starts turned off
red_led.value(0)
blue_led.value(0)

# Button flag set by Interrupt Service Routine (ISR)
button_triggered = False
last_interrupt_time = 0

# ISR Handler for the button press (falling edge: when button connects to GND)
def button_isr(pin):
    global button_triggered, last_interrupt_time, is_idle, red_start_time
    current_time = time.ticks_ms()
    # 200ms debounce filter
    if time.ticks_diff(current_time, last_interrupt_time) > 200:
        button_triggered = True
        last_interrupt_time = current_time
        
        # Instant hardware feedback: control LEDs immediately in ISR to bypass network latency
        if is_idle:
            red_led.value(1)
            blue_led.value(0)
            red_start_time = current_time
            is_idle = False
        elif blue_led.value() == 1:
            blue_led.value(0)
            red_led.value(1)
            red_start_time = current_time

# Attach hardware interrupt to the button pin
button.irq(trigger=machine.Pin.IRQ_FALLING, handler=button_isr)

# Helper function to update the server with the current state
def update_server_state(idle_val, remaining_val, led_val):
    global last_reported_idle, last_reported_remaining, last_reported_led, server_offline, last_offline_time
    if (idle_val != last_reported_idle or 
        remaining_val != last_reported_remaining or 
        led_val != last_reported_led):
        
        # If the server is offline, rate limit retries to once every 5 seconds
        if server_offline:
            if time.ticks_diff(time.ticks_ms(), last_offline_time) < 5000:
                return
                
        try:
            payload = {
                "is_idle": idle_val,
                "remaining_time": remaining_val,
                "active_led": led_val
            }
            res = urequests.post(SERVER_URL + "/api/state", json=payload)
            res.close()
            last_reported_idle = idle_val
            last_reported_remaining = remaining_val
            last_reported_led = led_val
            server_offline = False  # Connection successful, reset offline flag
        except Exception as e:
            print("Failed to send state update:", e)
            server_offline = True
            last_offline_time = time.ticks_ms()

# Helper function to connect to WiFi
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi (SSID: {})...".format(WIFI_SSID))
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        timeout = 15
        start = time.time()
        while not wlan.isconnected() and (time.time() - start) < timeout:
            time.sleep(0.5)
            print(".", end="")
        print("")
    if wlan.isconnected():
        print("Connected to WiFi! IP address:", wlan.ifconfig()[0])
    else:
        print("WiFi connection failed! Proceeding in offline mode.")

# --- INITIALIZATION ---
connect_wifi()

# Initial fetch of duration configuration
try:
    print("Fetching initial configuration from server...")
    res = urequests.get(SERVER_URL + "/api/config")
    data = res.json()
    res.close()
    red_duration_s = data.get("red_duration", 10)
    print("Initial Red LED duration set to:", red_duration_s)
except Exception as e:
    print("Could not fetch initial config, using default ({}s):".format(red_duration_s), e)

update_server_state(True, 0, "NONE")
last_config_check = time.ticks_ms()

print("System started. Waiting for button press...")

# --- MAIN LOOP ---
while True:
    # Capture and clear the button trigger flag locally
    pressed = False
    if button_triggered:
        pressed = True
        button_triggered = False  # Reset flag

    if is_idle:
        update_server_state(True, 0, "NONE")
        
        # Periodically poll server for duration configuration updates (every 5 seconds)
        if time.ticks_diff(time.ticks_ms(), last_config_check) >= 5000:
            last_config_check = time.ticks_ms()
            try:
                res = urequests.get(SERVER_URL + "/api/config")
                data = res.json()
                res.close()
                new_duration = data.get("red_duration", 10)
                if new_duration != red_duration_s:
                    red_duration_s = new_duration
                    print("Updated Red LED duration from server:", red_duration_s)
            except Exception as e:
                print("Failed to sync config:", e)

        if pressed:
            print("Button pressed: Turning on Red LED for {} seconds.".format(red_duration_s))
            
    else:
        elapsed_time = time.ticks_diff(time.ticks_ms(), red_start_time)
        red_duration_ms = red_duration_s * 1000
        
        if elapsed_time < red_duration_ms:
            # We are in the Red LED phase
            remaining_s = max(0, int((red_duration_ms - elapsed_time) / 1000))
            update_server_state(False, remaining_s, "RED")
        else:
            # We are in the Blue LED phase
            if blue_led.value() == 0:
                print("Timer finished: Switching to Blue LED.")
                red_led.value(0)
                blue_led.value(1)
                
            update_server_state(False, 0, "BLUE")
                
            if pressed:
                print("Button pressed in Blue: Restarting cycle to Red LED.")
                
    time.sleep(0.01)
