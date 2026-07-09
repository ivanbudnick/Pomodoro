from flask import Flask, jsonify, request, render_template
import os

app = Flask(__name__)

# Global configuration (in-memory storage)
config = {
    "red_duration": 10  # default duration in seconds
}

# Global ESP32 state (in-memory storage)
state = {
    "is_idle": True,
    "remaining_time": 0,
    "active_led": "NONE"  # Can be "RED", "BLUE", or "NONE"
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global config
    if request.method == 'POST':
        data = request.get_json() or {}
        if 'red_duration' in data:
            try:
                duration = int(data['red_duration'])
                if duration > 0:
                    config['red_duration'] = duration
                    return jsonify({"status": "success", "config": config})
                else:
                    return jsonify({"status": "error", "message": "Duration must be greater than 0"}), 400
            except ValueError:
                return jsonify({"status": "error", "message": "Invalid integer value"}), 400
        return jsonify({"status": "error", "message": "Missing red_duration parameter"}), 400
    
    return jsonify(config)

@app.route('/api/state', methods=['GET', 'POST'])
def api_state():
    global state
    if request.method == 'POST':
        data = request.get_json() or {}
        state['is_idle'] = data.get('is_idle', True)
        state['remaining_time'] = data.get('remaining_time', 0)
        state['active_led'] = data.get('active_led', 'NONE')
        return jsonify({"status": "success", "state": state})
        
    return jsonify(state)

if __name__ == '__main__':
    # Bind to 0.0.0.0 so that other devices on local network and ngrok/localtunnel can access it.
    app.run(host='0.0.0.0', port=5001, debug=True)
