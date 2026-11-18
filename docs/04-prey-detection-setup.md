# Step 4: Prey Detection Setup

This integrates the specialized prey detection AI to identify cats carrying mice, birds, or other prey.

## Prerequisites
- Completed [03-frigate-setup.md](03-frigate-setup.md)
- Python 3.9+ installed
- Cat detection working in Frigate

## 4.1 Clone BalrogCatPreyAnalyzer

```bash
cd /opt
git clone https://github.com/dieriver/BalrogCatPreyAnalyzer.git
cd BalrogCatPreyAnalyzer
```

## 4.2 Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install requirements
pip install -r requirements.txt

# Additional dependencies for our integration
pip install paho-mqtt requests
```

## 4.3 Configure Prey Analyzer

Create `config.yaml` in the BalrogCatPreyAnalyzer directory:

```yaml
# MQTT Configuration
mqtt:
  broker: "localhost"
  port: 1883
  username: ""  # If using authentication
  password: ""
  topic_subscribe: "frigate/events"
  topic_publish: "catflap/prey_detected"

# Frigate Configuration
frigate:
  url: "http://localhost:5000"
  
# Detection Settings
detection:
  confidence_threshold: 0.7
  prey_types:
    - mouse
    - bird
    - lizard
    - slow-worm

# Notifications
telegram:
  enabled: false  # Set to true to enable
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: "YOUR_CHAT_ID"
```

## 4.4 Integration Script

Copy `config/prey_detection_bridge.py` to connect Frigate events to the prey analyzer.

Run the bridge:

```bash
cd /opt/BalrogCatPreyAnalyzer
python prey_detection_bridge.py
```

## 4.5 Run as Service

Create systemd service for auto-start:

```bash
sudo nano /etc/systemd/system/prey-detection.service
```

```ini
[Unit]
Description=Cat Prey Detection Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/BalrogCatPreyAnalyzer
ExecStart=/opt/BalrogCatPreyAnalyzer/venv/bin/python prey_detection_bridge.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable prey-detection
sudo systemctl start prey-detection
```

## 4.6 Docker Alternative

Use the provided Dockerfile:

```bash
cd /path/to/CatMouseLLM
docker build -t prey-detection -f docker/Dockerfile.prey-detection .
docker run -d \
  --name prey-detection \
  --restart unless-stopped \
  --network host \
  prey-detection
```

## 4.7 Verify Integration

1. Check service is running:
   ```bash
   sudo systemctl status prey-detection
   ```

2. Monitor MQTT messages:
   ```bash
   mosquitto_sub -h localhost -t "catflap/#"
   ```

3. Check logs:
   ```bash
   journalctl -u prey-detection -f
   ```

## Testing

To test without waiting for your cat:

1. Download a test image of a cat with prey
2. Send to the analyzer API:
   ```bash
   curl -X POST http://localhost:8080/analyze \
     -F "image=@cat_with_mouse.jpg"
   ```

## Next Step

Return to the main [README](../README.md) to complete the automation setup in Home Assistant.
