# Step 3: Frigate NVR Setup

Frigate provides local AI-powered object detection for your NEST camera stream.

## Prerequisites
- Completed [02-home-assistant-setup.md](02-home-assistant-setup.md)
- Docker installed (or Home Assistant OS)

## 3.1 Install go2rtc

go2rtc converts your NEST camera stream to RTSP format that Frigate can use.

### Option A: Docker (Standalone)

```bash
docker run -d \
  --name go2rtc \
  --restart unless-stopped \
  -p 1984:1984 \
  -p 8554:8554 \
  -p 8555:8555/tcp \
  -p 8555:8555/udp \
  -v /path/to/config:/config \
  alexxit/go2rtc
```

### Option B: Home Assistant Add-on

1. Add repository: `https://github.com/AlexxIT/go2rtc`
2. Install **go2rtc** add-on
3. Start the add-on

### Configure go2rtc

Copy `config/go2rtc.yaml` to your go2rtc config directory and update with your credentials.

## 3.2 Install Frigate

### Option A: Docker

```bash
docker run -d \
  --name frigate \
  --restart unless-stopped \
  --shm-size=256m \
  -p 5000:5000 \
  -p 8971:8971 \
  -e FRIGATE_RTSP_PASSWORD='your_password' \
  -v /path/to/frigate/config:/config \
  -v /path/to/frigate/storage:/media/frigate \
  ghcr.io/blakeblackshear/frigate:stable
```

### Option B: Home Assistant Add-on

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Click ⋮ → **Repositories**
3. Add: `https://github.com/blakeblackshear/frigate-hass-addons`
4. Find **Frigate** and install
5. Configure and start

### Configure Frigate

Copy `config/frigate.yml` to your Frigate config directory and update camera settings.

## 3.3 Install Frigate HACS Integration

1. In Home Assistant, go to **HACS** → **Integrations**
2. Search for **Frigate**
3. Install and restart Home Assistant
4. Go to **Settings** → **Devices & Services**
5. Add **Frigate** integration
6. Enter your Frigate URL (e.g., `http://localhost:5000`)

## 3.4 Verify Cat Detection

1. Access Frigate UI: `http://your-server:5000`
2. You should see your camera feed
3. Wait for your cat to appear
4. Check that "cat" object is detected (bounding box appears)
5. Verify events appear in the Events tab

## Testing

```bash
# Test RTSP stream from go2rtc
ffplay rtsp://localhost:8554/nest_garden

# Check MQTT messages
mosquitto_sub -h localhost -t "frigate/events"
```

## Next Step

Continue to [04-prey-detection-setup.md](04-prey-detection-setup.md)
