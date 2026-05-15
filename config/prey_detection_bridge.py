#!/usr/bin/env python3
"""
Prey Detection Bridge

Listens for Frigate cat detection events via MQTT, fetches the snapshot,
sends it to the prey analyzer, and publishes results back to MQTT.

This bridges Frigate's general cat detection with the specialized
prey detection model from BalrogCatPreyAnalyzer.
"""

import json
import logging
import os
import sys
import time
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

import paho.mqtt.client as mqtt
import requests
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('prey_detection_bridge')

# Load configuration
CONFIG_PATH = Path(__file__).parent / 'config.yaml'
if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
else:
    # Default configuration
    config = {
        'mqtt': {
            'broker': os.getenv('MQTT_BROKER', 'localhost'),
            'port': int(os.getenv('MQTT_PORT', 1883)),
            'username': os.getenv('MQTT_USER', ''),
            'password': os.getenv('MQTT_PASSWORD', ''),
            'topic_subscribe': 'frigate/events',
            'topic_publish': 'catflap/prey_detected',
        },
        'frigate': {
            'url': os.getenv('FRIGATE_URL', 'http://localhost:5000'),
        },
        'detection': {
            'confidence_threshold': 0.7,
        }
    }


class PreyDetector:
    """Handles prey detection using BalrogCatPreyAnalyzer models."""
    
    def __init__(self, model_path: str = None):
        """Initialize the prey detector with optional model path."""
        self.model_path = model_path
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load the pre-trained prey detection model."""
        try:
            # Import the prey analyzer module
            # This assumes BalrogCatPreyAnalyzer is installed/available
            sys.path.insert(0, str(Path(__file__).parent))
            from cat_prey_analyzer import CatPreyAnalyzer
            self.model = CatPreyAnalyzer(self.model_path)
            logger.info("Prey detection model loaded successfully")
        except ImportError:
            logger.warning("CatPreyAnalyzer not found - using fallback API mode")
            self.model = None
        except Exception as e:
            logger.error(f"Failed to load prey detection model: {e}")
            self.model = None
    
    def analyze_image(self, image_bytes: bytes) -> dict:
        """
        Analyze an image for prey detection.
        
        Args:
            image_bytes: JPEG image as bytes
            
        Returns:
            dict with keys:
                - prey_detected: bool
                - confidence: float (0-1)
                - prey_type: str or None
        """
        if self.model:
            # Use local model
            try:
                result = self.model.analyze(image_bytes)
                return {
                    'prey_detected': result.get('has_prey', False),
                    'confidence': result.get('confidence', 0.0),
                    'prey_type': result.get('prey_type', None),
                }
            except Exception as e:
                logger.error(f"Model analysis failed: {e}")
        
        # Fallback: very basic check (for testing only)
        logger.warning("Using fallback detection - always returns no prey")
        return {
            'prey_detected': False,
            'confidence': 0.0,
            'prey_type': None,
        }


class PreyDetectionBridge:
    """Main bridge between Frigate events and prey detection."""
    
    CACHE_SIZE = 100

    def __init__(self, config: dict):
        self.config = config
        self.mqtt_client = None
        self.prey_detector = PreyDetector()
        self.frigate_url = config['frigate']['url']
        self.confidence_threshold = config['detection']['confidence_threshold']
        self._event_cache = OrderedDict()
        
    def connect_mqtt(self):
        """Establish MQTT connection."""
        self.mqtt_client = mqtt.Client(client_id="prey_detection_bridge")
        
        mqtt_config = self.config['mqtt']
        
        if mqtt_config.get('username'):
            self.mqtt_client.username_pw_set(
                mqtt_config['username'],
                mqtt_config.get('password', '')
            )
        
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_disconnect = self._on_disconnect
        
        logger.info(f"Connecting to MQTT broker at {mqtt_config['broker']}:{mqtt_config['port']}")
        self.mqtt_client.connect(mqtt_config['broker'], mqtt_config['port'], 60)
        
    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            topic = self.config['mqtt']['topic_subscribe']
            client.subscribe(topic)
            logger.info(f"Subscribed to {topic}")
        else:
            logger.error(f"Failed to connect to MQTT: {rc}")
            
    def _on_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection."""
        logger.warning(f"Disconnected from MQTT: {rc}")
        if rc != 0:
            logger.info("Attempting to reconnect...")
            
    def _on_message(self, client, userdata, msg):
        """Handle incoming Frigate events."""
        try:
            payload = json.loads(msg.payload.decode())
            self._process_event(payload)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in message: {msg.payload}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    def _process_event(self, event: dict):
        """Process a Frigate event for potential prey detection."""
        # Only process cat events
        if event.get('after', {}).get('label') != 'cat':
            return
            
        # Only process when cat enters frame or updates
        event_type = event.get('type')
        if event_type not in ['new', 'update', 'end']:
            return
            
        event_id = event.get('after', {}).get('id')
        if not event_id:
            return
            
        logger.info(f"Processing cat event: {event_id}")
        
        # Check cache first
        if event_id in self._event_cache:
            logger.info(f"Using cached result for event {event_id}")
            result = self._event_cache[event_id]
            # Move to end (most recently used)
            self._event_cache.move_to_end(event_id)
        else:
            # Fetch snapshot from Frigate
            snapshot = self._get_snapshot(event_id)
            if not snapshot:
                logger.warning(f"Could not get snapshot for event {event_id}")
                return

            # Analyze for prey
            result = self.prey_detector.analyze_image(snapshot)
            
            # Update cache
            self._event_cache[event_id] = result
            if len(self._event_cache) > self.CACHE_SIZE:
                self._event_cache.popitem(last=False)
        
        # Publish result
        self._publish_result(event_id, result)
        
    def _get_snapshot(self, event_id: str) -> bytes:
        """Fetch snapshot from Frigate API."""
        try:
            url = f"{self.frigate_url}/api/events/{event_id}/snapshot.jpg"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Failed to get snapshot: {response.status_code}")
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
        return None
        
    def _publish_result(self, event_id: str, result: dict):
        """Publish prey detection result to MQTT."""
        prey_detected = (
            result['prey_detected'] and 
            result['confidence'] >= self.confidence_threshold
        )
        
        message = {
            'event_id': event_id,
            'prey_detected': prey_detected,
            'confidence': result['confidence'],
            'prey_type': result['prey_type'],
            'timestamp': time.time(),
            'status': 'prey' if prey_detected else 'clear',
        }
        
        topic = self.config['mqtt']['topic_publish']
        self.mqtt_client.publish(topic, json.dumps(message), retain=False)
        
        if prey_detected:
            logger.warning(f"🐭 PREY DETECTED! Confidence: {result['confidence']:.2f}")
        else:
            logger.info(f"Cat clear - no prey detected")
            
    def run(self):
        """Start the bridge main loop."""
        self.connect_mqtt()
        
        try:
            self.mqtt_client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.mqtt_client.disconnect()


def main():
    """Entry point."""
    logger.info("Starting Prey Detection Bridge")
    logger.info(f"Frigate URL: {config['frigate']['url']}")
    logger.info(f"MQTT Broker: {config['mqtt']['broker']}")
    
    bridge = PreyDetectionBridge(config)
    bridge.run()


if __name__ == '__main__':
    main()
