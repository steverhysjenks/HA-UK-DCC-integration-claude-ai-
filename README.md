# Hildebrand Glow (DCC) — Home Assistant Integration

The source is from the link repo below (hildebrand). As it is abandond I am attempting using Claude.ai to update it for my use only.

A Home Assistant custom integration that pulls **electricity and gas consumption data** from UK SMETS smart meters via the **Hildebrand Glow / Glowmarkt API** (Data Communications Company backend).

> **Data is delayed ~30 minutes** due to the DCC polling cycle. For real-time data, see [ha_hildebrand_glow_ihd_mqtt](https://github.com/megakid/ha_hildebrand_glow_ihd_mqtt).

---

## Prerequisites

1. A **SMETS2** (or enrolled SMETS1) smart meter in your home.
2. A free **Bright** account — download the app ([Android](https://play.google.com/store/apps/details?id=uk.co.hildebrand.brightionic) / [iOS](https://apps.apple.com/gb/app/bright/id1369989022)) and complete the DCC verification.
3. Wait until you can see your data in the Bright app before configuring this integration.

---

## Installation

### HACS (recommended)

1. In HACS → Integrations → ⋮ → *Custom repositories*.
2. Add `https://github.com/steverhysjenks/HA-UK-DCC-integration-claude-ai` with category **Integration**.
3. Search for *Hildebrand Glow (DCC)* and install.
4. Restart Home Assistant.

### Manual

Copy `custom_components/hildebrandglow_dcc/` into your HA `config/custom_components/` folder and restart.

---

## Configuration

After restarting, go to **Settings → Devices & Services → Add Integration**, search for *Hildebrand Glow (DCC)* and enter your Bright account email and password.

---

## Sensors

One set of sensors is created per meter installation (virtual entity) on your account.

| Sensor | Unit | HA Device Class | Notes |
|---|---|---|---|
| Electricity Usage Today | kWh | Energy | TOTAL_INCREASING |
| Electricity Cost Today | GBP | Monetary | pence→GBP converted |
| Gas Usage Today | kWh | Energy | TOTAL_INCREASING |
| Gas Cost Today | GBP | Monetary | pence→GBP converted |
| Electricity Export Today | kWh | Energy | Disabled by default |

Sensors reset shortly after 01:30 (to ensure the prior day's last half-hourly slot has propagated).

---

## Energy Dashboard

These sensors work natively with HA's [Energy Management](https://www.home-assistant.io/docs/energy/) dashboard.

---

## API Details

- **Base URL**: `https://api.glowmarkt.com/api/v0-1`
- **Auth**: JWT via `POST /auth` (token valid 7 days; auto-refreshed)
- **applicationId**: `b0f1b774-a586-4f72-9edd-27ead8aa7a8d` (Bright individual user)
- **Docs**: [Glowmarkt API v1.8 (April 2026)](https://docs.glowmarkt.com/GlowmarktAPIDataRetrievalDocumentationIndividualUserForBright.pdf)

---

## Debugging

```yaml
logger:
  default: warning
  logs:
    custom_components.hildebrandglow_dcc: debug
```

---

## Licence

MIT
