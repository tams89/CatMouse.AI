#!/usr/bin/env python3
"""
CatMouse.AI - Prey Detection Bridge
====================================
Bridges camera motion events, cloud/local Vision Language Models (Gemini / Ollama),
and Home Assistant via MQTT to lock the cat flap when a cat carries prey.

Supported Inference Providers:
  - "gemini": Google Gemini 2.5 Flash API (Cloud VLM, ~800ms, resilient to garden camera angles)
  - "ollama": Local Ollama instance e.g. Qwen2.5-VL / Llama3.2-Vision on local RTX 3090 GPU
  - "dummy": Deterministic test mode for verification without cloud API keys
"""

import argparse
import base64
import json
import logging
import os
import sys
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('catmouse_bridge')

# Try importing paho.mqtt (optional for CLI test mode)
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not installed; running in HTTP/CLI only mode")

CONFIG_PATH = Path(__file__).parent / 'prey_detection_config.yaml'
ENV_PATH = Path(__file__).parent.parent / '.env'


def load_dotenv():
    """Simple parser to load .env into os.environ if present without external dependency."""
    if ENV_PATH.exists():
        try:
            with open(ENV_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            logger.warning(f"Could not load .env file: {e}")


load_dotenv()


def load_config() -> Dict[str, Any]:
    """Loads configuration with environment variable overrides."""
    config: Dict[str, Any] = {
        'provider': os.getenv('DETECTION_PROVIDER', 'gemini'),
        'gemini': {
            'api_key': os.getenv('GEMINI_API_KEY', ''),
            'model': os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'),
            'timeout_seconds': 6,
        },
        'ollama': {
            'host': os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
            'model': os.getenv('OLLAMA_MODEL', 'qwen2.5-vl:7b'),
            'timeout_seconds': 10,
        },
        'detection': {
            'confidence_threshold': float(os.getenv('CONFIDENCE_THRESHOLD', '0.7')),
        },
        'mqtt': {
            'broker': os.getenv('MQTT_BROKER', 'localhost'),
            'port': int(os.getenv('MQTT_PORT', '1883')),
            'username': os.getenv('MQTT_USER', ''),
            'password': os.getenv('MQTT_PASSWORD', ''),
            'topic_subscribe': os.getenv('MQTT_SUB_TOPIC', 'frigate/events'),
            'topic_publish': os.getenv('MQTT_PUB_TOPIC', 'catflap/prey_detected'),
        },
        'server': {
            'host': os.getenv('SERVER_HOST', '0.0.0.0'),
            'port': int(os.getenv('SERVER_PORT', '8095')),
        },
        'homeassistant': {
            'snapshot_path': os.getenv(
                'HA_SNAPSHOT_PATH',
                '/config/www/prey_detection/latest.jpg'
            ),
        }
    }

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    for k, v in file_config.items():
                        if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                            config[k].update(v)
                        else:
                            config[k] = v
        except Exception as e:
            logger.error(f"Error reading {CONFIG_PATH}: {e}")

    # Environment variables take precedence over yaml
    if os.getenv('GEMINI_API_KEY'):
        config['gemini']['api_key'] = os.getenv('GEMINI_API_KEY')
    if os.getenv('DETECTION_PROVIDER'):
        config['provider'] = os.getenv('DETECTION_PROVIDER')
    if os.getenv('MQTT_BROKER'):
        config['mqtt']['broker'] = os.getenv('MQTT_BROKER')
    if os.getenv('MQTT_USER'):
        config['mqtt']['username'] = os.getenv('MQTT_USER')
    if os.getenv('MQTT_PASSWORD'):
        config['mqtt']['password'] = os.getenv('MQTT_PASSWORD')
    if os.getenv('MQTT_PORT'):
        config['mqtt']['port'] = int(os.getenv('MQTT_PORT'))
    if os.getenv('SERVER_PORT'):
        config['server']['port'] = int(os.getenv('SERVER_PORT'))
    if os.getenv('HA_SNAPSHOT_URL'):
        config['homeassistant']['snapshot_url'] = os.getenv('HA_SNAPSHOT_URL')

    return config


class VisionPreyDetector:
    """Multi-modal Vision Language Model Prey Detector."""

    SYSTEM_PROMPT = (
        "You are an expert domestic animal behavioral and prey classification system. "
        "Analyze this camera snapshot of a domestic cat near a cat flap or in a garden. "
        "Answer the following questions strictly in JSON format:\n"
        "1. is_cat: Is there a cat visible in this image? (boolean)\n"
        "2. has_prey: Is the cat holding, carrying, or interacting with any prey (mouse, rat, bird, lizard, rabbit, frog) in its mouth or paws? (boolean)\n"
        "3. confidence: What is your confidence (0.0 to 1.0) that the cat is carrying prey? (0.0 if no prey is visible)\n"
        "4. prey_type: What kind of prey is it? null if no prey, or one of: 'mouse', 'rat', 'bird', 'lizard', 'rabbit', 'other'\n"
        "5. description: A concise 1-sentence description of what the cat is doing and holding.\n"
        "Respond ONLY with valid JSON with keys: is_cat, has_prey, confidence, prey_type, description."
    )

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = config.get('provider', 'gemini').lower()
        self.http_session = requests.Session()

    def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Dispatches image analysis to the configured provider."""
        if not image_bytes or len(image_bytes) < 100:
            return {
                'is_cat': False,
                'prey_detected': False,
                'confidence': 0.0,
                'prey_type': None,
                'description': 'Empty or invalid image data',
            }

        if self.provider == 'gemini':
            return self._analyze_gemini(image_bytes)
        elif self.provider == 'ollama':
            return self._analyze_ollama(image_bytes)
        elif self.provider == 'dummy':
            return self._analyze_dummy(image_bytes)
        else:
            logger.error(f"Unknown provider '{self.provider}', falling back to dummy")
            return self._analyze_dummy(image_bytes)

    def _analyze_gemini(self, image_bytes: bytes) -> Dict[str, Any]:
        """Calls Google Gemini Vision API."""
        api_key = self.config.get('gemini', {}).get('api_key', '').strip()
        if not api_key:
            logger.warning("No GEMINI_API_KEY configured. Falling back to dummy mode.")
            return self._analyze_dummy(image_bytes)

        model = self.config.get('gemini', {}).get('model', 'gemini-2.5-flash')
        timeout = self.config.get('gemini', {}).get('timeout_seconds', 6)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        b64_image = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": self.SYSTEM_PROMPT},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image,
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            }
        }

        try:
            start_t = time.time()
            resp = self.http_session.post(url, json=payload, timeout=timeout)
            duration = time.time() - start_t
            logger.info(f"Gemini API answered in {duration:.2f}s (HTTP {resp.status_code})")

            if resp.status_code != 200:
                logger.error(f"Gemini API error ({resp.status_code}): {resp.text[:300]}")
                return self._fallback_result(f"Gemini API returned status {resp.status_code}")

            data = resp.json()
            candidates = data.get('candidates', [])
            if not candidates:
                return self._fallback_result("No candidates returned from Gemini")

            text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '{}')
            result_json = json.loads(text)

            prey_detected = bool(result_json.get('has_prey', False))
            confidence = float(result_json.get('confidence', 0.0))

            return {
                'is_cat': bool(result_json.get('is_cat', False)),
                'prey_detected': prey_detected,
                'confidence': confidence,
                'prey_type': result_json.get('prey_type'),
                'description': result_json.get('description', ''),
            }
        except Exception as e:
            logger.error(f"Gemini analysis exception: {e}")
            return self._fallback_result(str(e))

    def _analyze_ollama(self, image_bytes: bytes) -> Dict[str, Any]:
        """Calls local Ollama VLM (RTX 3090 backup)."""
        host = self.config.get('ollama', {}).get('host', 'http://localhost:11434').rstrip('/')
        model = self.config.get('ollama', {}).get('model', 'qwen2.5-vl:7b')
        timeout = self.config.get('ollama', {}).get('timeout_seconds', 10)
        url = f"{host}/api/generate"

        b64_image = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            "model": model,
            "prompt": self.SYSTEM_PROMPT,
            "images": [b64_image],
            "stream": False,
            "format": "json",
        }

        try:
            start_t = time.time()
            resp = self.http_session.post(url, json=payload, timeout=timeout)
            duration = time.time() - start_t
            logger.info(f"Ollama answered in {duration:.2f}s (HTTP {resp.status_code})")

            if resp.status_code != 200:
                logger.error(f"Ollama error ({resp.status_code}): {resp.text[:200]}")
                return self._fallback_result(f"Ollama error {resp.status_code}")

            data = resp.json()
            result_json = json.loads(data.get('response', '{}'))

            return {
                'is_cat': bool(result_json.get('is_cat', False)),
                'prey_detected': bool(result_json.get('has_prey', False)),
                'confidence': float(result_json.get('confidence', 0.0)),
                'prey_type': result_json.get('prey_type'),
                'description': result_json.get('description', ''),
            }
        except Exception as e:
            logger.error(f"Ollama analysis exception: {e}")
            return self._fallback_result(str(e))

    def _analyze_dummy(self, image_bytes: bytes) -> Dict[str, Any]:
        """Deterministic dummy mode for integration testing."""
        logger.info("Executing dummy detection (no API called)")
        return {
            'is_cat': True,
            'prey_detected': False,
            'confidence': 0.1,
            'prey_type': None,
            'description': 'Dummy mode: cat present, no prey detected',
        }

    def _fallback_result(self, err_msg: str) -> Dict[str, Any]:
        return {
            'is_cat': False,
            'prey_detected': False,
            'confidence': 0.0,
            'prey_type': None,
            'description': f"Inference failed: {err_msg}",
        }


class PreyDetectionBridge:
    """Main orchestration bridge handling MQTT, Webhooks, and Home Assistant coordination."""

    CACHE_SIZE = 100

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.detector = VisionPreyDetector(config)
        self.confidence_threshold = config['detection']['confidence_threshold']
        self._event_cache: OrderedDict = OrderedDict()
        self.mqtt_client: Optional[Any] = None

    def connect_mqtt(self):
        """Connects to Homelab Mosquitto MQTT broker."""
        if not MQTT_AVAILABLE:
            return

        mqtt_config = self.config['mqtt']
        self.mqtt_client = mqtt.Client(client_id="catmouse_bridge")

        if mqtt_config.get('username'):
            self.mqtt_client.username_pw_set(
                mqtt_config['username'],
                mqtt_config.get('password', '')
            )

        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message

        try:
            logger.info(f"Connecting to MQTT {mqtt_config['broker']}:{mqtt_config['port']}")
            self.mqtt_client.connect(mqtt_config['broker'], mqtt_config['port'], 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            logger.warning(f"Could not connect to MQTT broker: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            topic = self.config['mqtt']['topic_subscribe']
            client.subscribe(topic)
            logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"MQTT connect failed with return code {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            self.process_event(payload)
        except Exception as e:
            logger.error(f"MQTT message parsing error: {e}")

    def process_event(self, event: Dict[str, Any]):
        """Processes Frigate or Home Assistant cat motion event."""
        label = event.get('after', {}).get('label')
        if label and label != 'cat':
            return

        event_id = event.get('after', {}).get('id') or f"evt_{int(time.time())}"
        snapshot_bytes = None

        # Check snapshot URL if supplied
        snapshot_url = event.get('snapshot_url')
        if snapshot_url:
            try:
                r = requests.get(snapshot_url, timeout=5)
                if r.status_code == 200:
                    snapshot_bytes = r.content
            except Exception as e:
                logger.error(f"Failed to fetch snapshot from {snapshot_url}: {e}")

        # Fallback to local Home Assistant snapshot file
        if not snapshot_bytes:
            ha_path = Path(self.config['homeassistant']['snapshot_path'])
            if ha_path.exists():
                try:
                    snapshot_bytes = ha_path.read_bytes()
                except Exception as e:
                    logger.error(f"Failed to read local snapshot {ha_path}: {e}")

        if not snapshot_bytes:
            logger.warning(f"No snapshot data available for event {event_id}")
            return

        self.evaluate_and_publish(event_id, snapshot_bytes)

    def evaluate_and_publish(self, event_id: str, image_bytes: bytes) -> Dict[str, Any]:
        """Runs inference and publishes determination to MQTT."""
        result = self.detector.analyze_image(image_bytes)

        prey_detected = (
            result['prey_detected'] and
            result['confidence'] >= self.confidence_threshold
        )

        message = {
            'event_id': event_id,
            'is_cat': result['is_cat'],
            'prey_detected': prey_detected,
            'confidence': round(result['confidence'], 2),
            'prey_type': result['prey_type'],
            'description': result['description'],
            'timestamp': int(time.time()),
            'status': 'prey' if prey_detected else 'clear',
        }

        # Publish to MQTT topic
        if self.mqtt_client and self.mqtt_client.is_connected():
            topic = self.config['mqtt']['topic_publish']
            self.mqtt_client.publish(topic, json.dumps(message), retain=False)
            logger.info(f"Published detection to MQTT [{topic}]: status={message['status']}")

        if prey_detected:
            logger.warning(
                f"🚨 PREY DETECTED! Type: {result['prey_type']}, "
                f"Confidence: {result['confidence']:.2f}. Triggering flap lock."
            )
        else:
            logger.info(f"Cat evaluated: clear (confidence: {result['confidence']:.2f})")

        return message


def run_http_server(bridge: PreyDetectionBridge, host: str, port: int):
    """Runs lightweight HTTP Webhook receiver."""

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'healthy',
                    'provider': bridge.detector.provider,
                    'timestamp': int(time.time())
                }).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path in ('/analyze', '/webhook/garden_motion'):
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length) if content_length > 0 else b''

                image_bytes = None
                event_id = f"snap_{int(time.time())}"
                content_type = self.headers.get('Content-Type', '')

                data = {}
                if 'image/' in content_type:
                    image_bytes = body
                elif 'application/json' in content_type and body:
                    try:
                        data = json.loads(body.decode('utf-8'))
                        if 'event_id' in data:
                            event_id = str(data['event_id'])
                        if 'image_b64' in data:
                            image_bytes = base64.b64decode(data['image_b64'])
                        elif 'file_path' in data:
                            image_bytes = Path(data['file_path']).read_bytes()
                    except Exception as e:
                        logger.error(f"JSON payload parse error: {e}")

                # If image not directly provided, fetch via HTTP snapshot_url or attachment_url
                if not image_bytes:
                    ha_url = (
                        data.get('attachment_url') or
                        data.get('snapshot_url') or
                        data.get('image_url') or
                        bridge.config.get('homeassistant', {}).get('snapshot_url')
                    )
                    if ha_url:
                        try:
                            headers = {}
                            ha_token = os.environ.get('HA_TOKEN') or bridge.config.get('homeassistant', {}).get('access_token')
                            if ha_token and not str(ha_url).endswith('/local/prey_detection/latest.jpg'):
                                headers['Authorization'] = f"Bearer {ha_token}"
                            resp = requests.get(ha_url, headers=headers, timeout=5)
                            if resp.status_code == 200:
                                image_bytes = resp.content
                                logger.info(f"Fetched snapshot from URL: {ha_url} ({len(image_bytes)} bytes)")
                            else:
                                logger.warning(f"Failed to fetch {ha_url}: HTTP {resp.status_code}")
                        except Exception as e:
                            logger.error(f"Error fetching snapshot from {ha_url}: {e}")

                # Default fallback: read local snapshot path
                if not image_bytes:
                    ha_snap_path = bridge.config.get('homeassistant', {}).get('snapshot_path')
                    if ha_snap_path and Path(ha_snap_path).exists():
                        image_bytes = Path(ha_snap_path).read_bytes()

                if not image_bytes:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"error": "No image provided or found on disk"}')
                    return

                result = bridge.evaluate_and_publish(event_id, image_bytes)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # Suppress normal HTTP access log noise
            return

    server = HTTPServer((host, port), WebhookHandler)
    logger.info(f"Webhook HTTP server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down HTTP server...")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="CatMouse.AI Prey Detection Bridge")
    parser.add_argument('--image', type=str, help="Run one-shot detection on local image file")
    parser.add_argument('--provider', type=str, choices=['gemini', 'ollama', 'dummy'], help="Override detection provider")
    parser.add_argument('--publish-mqtt', action='store_true', help="Publish result to MQTT even in CLI test mode")
    parser.add_argument('--mock-prey', action='store_true', help="Simulate a prey detection event and publish to MQTT")
    parser.add_argument('--mock-clear', action='store_true', help="Simulate a cat clear event and publish to MQTT")
    args = parser.parse_args()

    config = load_config()
    if args.provider:
        config['provider'] = args.provider

    bridge = PreyDetectionBridge(config)

    # Simulation modes for testing Home Assistant automations
    if args.mock_prey:
        logger.info("Triggering mock PREY detected event to MQTT...")
        bridge.connect_mqtt()
        time.sleep(1)
        mock_msg = {
            'event_id': f"mock_prey_{int(time.time())}",
            'is_cat': True,
            'prey_detected': True,
            'confidence': 0.95,
            'prey_type': 'mouse',
            'description': 'MOCK TEST: Cat carrying field mouse',
            'timestamp': int(time.time()),
            'status': 'prey',
        }
        if bridge.mqtt_client:
            topic = config['mqtt']['topic_publish']
            bridge.mqtt_client.publish(topic, json.dumps(mock_msg))
            logger.info(f"Mock prey message published to {topic}")
            time.sleep(1)
            bridge.mqtt_client.loop_stop()
        return

    if args.mock_clear:
        logger.info("Triggering mock CLEAR event to MQTT...")
        bridge.connect_mqtt()
        time.sleep(1)
        mock_msg = {
            'event_id': f"mock_clear_{int(time.time())}",
            'is_cat': True,
            'prey_detected': False,
            'confidence': 0.05,
            'prey_type': None,
            'description': 'MOCK TEST: Cat approaching empty-mouthed',
            'timestamp': int(time.time()),
            'status': 'clear',
        }
        if bridge.mqtt_client:
            topic = config['mqtt']['topic_publish']
            bridge.mqtt_client.publish(topic, json.dumps(mock_msg))
            logger.info(f"Mock clear message published to {topic}")
            time.sleep(1)
            bridge.mqtt_client.loop_stop()
        return

    # One-shot image test
    if args.image:
        img_path = Path(args.image)
        if not img_path.exists():
            logger.error(f"Image not found: {img_path}")
            sys.exit(1)
        if args.publish_mqtt:
            bridge.connect_mqtt()
            time.sleep(0.5)
        res = bridge.evaluate_and_publish(f"cli_{int(time.time())}", img_path.read_bytes())
        print(json.dumps(res, indent=2))
        return

    # Full server mode
    bridge.connect_mqtt()
    srv_cfg = config['server']
    run_http_server(bridge, srv_cfg['host'], srv_cfg['port'])


if __name__ == '__main__':
    main()
