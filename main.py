import machine
import time
import network
import urequests

# --- WIFI & SERVER CONFIGURATION ---
WIFI_SSID = "Wokwi-GUEST"  # Default SSID for Wokwi simulation
WIFI_PASSWORD = ""         # Wokwi-GUEST has no password
# Replace this URL with your localtunnel or ngrok public URL (e.g., "https://xxxx.loca.lt")
SERVER_URL = "http://YOUR_SERVER_ADDRESS_HERE" 

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
red_duration_s = 10  # Default duration in seconds (synced from server)

# Track last reported state to avoid redundant HTTP requests
last_reported_idle = None
last_reported_remaining = None
last_reported_led = None

# Ensure everything starts turned off
red_led.value(0)
blue_led.value(0)

# Helper function to update the server with the current state
def update_server_state(idle_val, remaining_val, led_val):
    global last_reported_idle, last_reported_remaining, last_reported_led
    # Only make HTTP request if the state has actually changed
    if (idle_val != last_reported_idle or 
        remaining_val != last_reported_remaining or 
        led_val != last_reported_led):
        try:
            payload = {
                "is_idle": idle_val,
                "remaining_time": remaining_val,
                "active_led": led_val
            }
            res = urequests.post(SERVER_URL + "/api/state", json=payload)
            res.close()  # Always close connections in MicroPython to free sockets
            last_reported_idle = idle_val
            last_reported_remaining = remaining_val
            last_reported_led = led_val
        except Exception as e:
            # Print warning but keep running (robust in case server is down)
            print("Failed to send state update:", e)

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

# Initialize server state representation
update_server_state(True, 0, "NONE")

last_config_check = 0
print("System started. Waiting for button press...")

# --- MAIN LOOP ---
while True:
    # Read button (with PULL_UP, 0 means pressed)
    button_pressed = (button.value() == 0)
    
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

        if button_pressed:
            print("Button pressed: Turning on Red LED for {} seconds.".format(red_duration_s))
            red_led.value(1)
            blue_led.value(0)
            red_start_time = time.ticks_ms()  # Save the current millisecond
            is_idle = False
            time.sleep(0.2)  # Avoid repeated instantaneous readings
            
    else:
        # If not idle, determine the state based on the elapsed time
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
                
            if button_pressed:
                print("Button pressed in Blue: Restarting cycle to Red LED.")
                blue_led.value(0)
                red_led.value(1)
                red_start_time = time.ticks_ms()  # Restart the timer
                time.sleep(0.2)  # Avoid repeated instantaneous readings
                
    # Small pause to avoid overloading the simulation processor
    time.sleep(0.01)
