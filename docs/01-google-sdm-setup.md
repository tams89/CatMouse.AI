# Step 1: Google SDM API Setup

This enables Home Assistant to access your NEST camera stream.

## Prerequisites
- Google account linked to your NEST devices
- $5 USD (one-time fee)

## Steps

### 1.1 Register for Device Access

1. Go to [Google Device Access Console](https://console.nest.google.com/device-access)
2. Click **"Go to the Device Access Console"**
3. Accept the Terms of Service
4. Pay the $5 one-time fee

### 1.2 Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **"Select a project"** → **"New Project"**
3. Name it `cat-prey-detection`
4. Click **"Create"**
5. **Note down your Project ID** (looks like `cat-prey-detection-123456`)

### 1.3 Enable Required APIs

In Google Cloud Console:

1. Go to **APIs & Services** → **Library**
2. Search and enable:
   - **Smart Device Management API**
   - **Cloud Pub/Sub API**

### 1.4 Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **"External"** → Click **"Create"**
3. Fill in:
   - App name: `Cat Prey Detection`
   - User support email: (your email)
   - Developer contact: (your email)
4. Click **"Save and Continue"** through remaining steps
5. No scopes needed, click through to **"Test users"**
6. Add your Google email as a test user

### 1.5 Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **"Create Credentials"** → **"OAuth client ID"**
3. Application type: **Web application**
4. Name: `Home Assistant`
5. Under **Authorized redirect URIs**, add:
   ```
   https://my.home-assistant.io/redirect/oauth
   ```
6. Click **"Create"**
7. **Save your Client ID and Client Secret** - you'll need these!

### 1.6 Create Device Access Project

1. Return to [Device Access Console](https://console.nest.google.com/device-access/project-list)
2. Click **"Create project"**
3. Name: `Cat Prey Detection`
4. Paste your **OAuth Client ID** from step 1.5
5. Leave **"Enable events"** unchecked (we'll use Frigate instead)
6. Click **"Create project"**
7. **Note down your Project ID** (different from Cloud Project ID)

### 1.7 Create Pub/Sub Subscription

1. Go to [Pub/Sub Console](https://console.cloud.google.com/cloudpubsub)
2. Click **"Create subscription"**
3. Subscription ID: `cat-prey-detection-sub`
4. For topic, select **"Enter topic manually"**
5. The topic URL is shown in your Device Access project (format: `projects/sdm-prod/topics/...`)
6. Click **"Create"**

## What You Should Have

| Item | Where to Find | Example |
|------|---------------|---------|
| OAuth Client ID | Cloud Console → Credentials | `123456789.apps.googleusercontent.com` |
| OAuth Client Secret | Cloud Console → Credentials | `GOCSPX-xxxxx` |
| Device Access Project ID | Device Access Console | `abc123-def456-...` |
| Cloud Project ID | Cloud Console | `cat-prey-detection-123456` |

## Next Step

Continue to [02-home-assistant-setup.md](02-home-assistant-setup.md)
