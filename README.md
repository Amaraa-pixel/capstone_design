# capstone_design

Simple Flask demo app that registers users, shows profiles, and displays a device dashboard backed by SQLite.

## Setup
1. Create a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Run
```bash
python app.py
```
Then open http://localhost:5000/ in your browser.

## Home Assistant webhook for live P110M updates
Expose the Flask app to your Home Assistant OS network and set a shared token (optional but recommended). You can also override the defaults so the UI shows your Tapo plug name and serial:

```bash
export PLUG_DEVICE_NAME="Tapo P110M Matter Plug"
export PLUG_SERIAL="P110M-01"
export WEBHOOK_TOKEN="your-secret-token"
python app.py
```

Create a REST command in Home Assistant that calls the webhook whenever the plug state changes:

```yaml
rest_command:
  send_p110m_state:
    url: "http://YOUR_FLASK_HOST:5000/api/plug-update"
    method: post
    headers:
      Content-Type: application/json
      X-Webhook-Token: "your-secret-token"
    payload: >-
      {
        "serial": "P110M-01",
        "state": "{{ states('switch.p110m') }}",
        "power_w": {{ state_attr('switch.p110m', 'current_power_w') | default(0) }},
        "energy_kwh": {{ state_attr('switch.p110m', 'today_energy_kwh') | default(0) }},
        "tamper": {{ is_state('binary_sensor.p110m_tamper', 'on') }},
        "abnormal": {{ is_state('binary_sensor.p110m_abnormal', 'on') }}
      }
```

Call `rest_command.send_p110m_state` from an automation that triggers on the plug turning on/off. The `/plug-timeline` page auto-refreshes every 5 seconds and will display the new state transitions and metrics.

### Abnormal toggle alerts via email
If the plug is toggled rapidly (default: 5 or more state changes within 5 seconds), the webhook marks an abnormal alert in the dashboard and emails a notification. Configure SMTP and recipient details through environment variables before starting the app:

```bash
export SMTP_SERVER="smtp.yourprovider.com"
export SMTP_PORT=587
export SMTP_USERNAME="smtp-user"
export SMTP_PASSWORD="smtp-password"
export SMTP_FROM="alerts@example.com"
export ALERT_EMAIL_TO="you@example.com"
# Optional tuning
export TOGGLE_WINDOW_SECONDS=5
export TOGGLE_THRESHOLD=5
```

If SMTP variables are omitted, alerts are logged to the console instead of emailed.

## Add a Tapo P110M Matter plug without Home Assistant
If you manage the Tapo plug directly (Matter or local API), you can still feed the dashboard by POSTing to the webhook endpoint yourself:

```bash
curl -X POST "http://YOUR_FLASK_HOST:5000/api/plug-update" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: your-secret-token" \
  -d '{
    "serial": "P110M-01",
    "state": "on",
    "power_w": 15.2,
    "energy_kwh": 0.43,
    "tamper": false,
    "abnormal": false
  }'
```

Every call inserts a timeline point plus dashboard metrics under the plug name you configured via `PLUG_DEVICE_NAME`.
