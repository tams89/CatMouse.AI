# Step 2: Home Assistant Setup

Configure Home Assistant with NEST camera and SureFlap integrations.

## Prerequisites
- Completed [01-google-sdm-setup.md](01-google-sdm-setup.md)
- Home Assistant running with external HTTPS access
- MQTT broker (Mosquitto) - install via Add-ons if not present

## 2.1 Install MQTT Broker

If you don't have MQTT yet:

1. In HA: **Settings** → **Add-ons** → **Add-on Store**
2. Search for **"Mosquitto broker"**
3. Click **Install** → **Start**
4. Enable **"Start on boot"**

## 2.2 Add Nest Integration

1. Access Home Assistant via your **external URL** (important!)
2. Go to **Settings** → **Devices & Services**
3. Click **"Add Integration"** → Search **"Nest"**
4. Select **"Nest"** (the SDM-based one)
5. Enter:
   - **Client ID**: (from Google Cloud Credentials)
   - **Client Secret**: (from Google Cloud Credentials)
   - **Project ID**: (from Device Access Console)
6. Click **"Submit"**
7. You'll be redirected to Google - sign in and authorize
8. Select your camera when prompted

### Troubleshooting

| Error | Solution |
|-------|----------|
| `400: invalid_request` | Use external URL, not `http://homeassistant.local` |
| `403: Forbidden` | Ensure SDM API is enabled in Cloud Console |
| Camera not listed | Re-authorize in Google Home app Partner Connections |

## 2.3 Add Sure Petcare Integration

1. Go to **Settings** → **Devices & Services**
2. Click **"Add Integration"** → Search **"Sure Petcare"**
3. Enter your Sure Petcare account credentials
4. Your SureFlap Connect should appear

### Find Your Flap ID

1. Go to Sure Petcare web: https://www.surepetcare.io/
2. Login and navigate to your cat flap
3. The URL will contain your flap ID: `.../flap/123456`
4. Note this down for automations

## 2.4 Verify Setup

After setup, you should have these entities:

```yaml
# Camera
camera.garden_camera  # (or similar name)

# Cat flap
lock.sureflap_cat_flap
sensor.sureflap_cat_flap_status

# Your cats
sensor.whiskers_location  # (your cat's name)
```

Test the camera stream:
1. Go to **Overview** dashboard
2. Add a **Picture Entity Card**
3. Select your NEST camera
4. Verify you can see live feed

## 2.5 Copy Configuration Files

Copy the Home Assistant config files from this repo:

```bash
# From the CatMouseLLM directory
cp config/homeassistant/*.yaml /config/packages/
```

Or manually create them in your `configuration.yaml`:

```yaml
# configuration.yaml
homeassistant:
  packages: !include_dir_named packages
```

Then copy contents from `config/homeassistant/` to `/config/packages/`

## Next Step

Continue to [03-frigate-setup.md](03-frigate-setup.md)
