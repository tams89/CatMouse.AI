# Cat Prey Detection System

Automatically detects when your cat is carrying prey and locks your SureFlap Connect cat flap.

## Architecture

```
NEST Cam → Google SDM API → Home Assistant → Frigate → Prey Detection → SureFlap Lock
```

## Quick Start

1. **Google SDM Setup** - See [docs/01-google-sdm-setup.md](docs/01-google-sdm-setup.md)
2. **Home Assistant Config** - See [docs/02-home-assistant-setup.md](docs/02-home-assistant-setup.md)
3. **Frigate Setup** - See [docs/03-frigate-setup.md](docs/03-frigate-setup.md)
4. **Prey Detection** - See [docs/04-prey-detection-setup.md](docs/04-prey-detection-setup.md)

## Components

| Component | Purpose | Config File |
|-----------|---------|-------------|
| go2rtc | NEST → RTSP converter | `config/go2rtc.yaml` |
| Frigate | Cat detection NVR | `config/frigate.yml` |
| Home Assistant | Automations | `config/homeassistant/` |

## Requirements

- Home Assistant (running instance)
- SureFlap Connect cat flap
- NEST Camera (with SDM API access - $5 one-time fee)
- Docker or Home Assistant OS (for running Frigate)
