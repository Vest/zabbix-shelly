# Dashboards

Global (fleet) dashboards for the Shelly hosts. Unlike templates, Zabbix global
dashboards are **not** part of `configuration.export`, so these are stored as
portable JSON (server-specific ids stripped) suitable for the `dashboard.create`
API method.

## shelly_fleet_overview.json

One screen for all Shelly devices (filtered by the `Shellies` host group), using
item-name **patterns** so new devices are picked up automatically:

- **Shelly problems** — live problems for the `Shellies` group.
- **Top power consumers (now)** — hosts ranked by current active power.
- **Active power — all Shellies (24h)** — `*: Active power` across pm1/cover/switch.
- **WiFi RSSI (7d)** — `WiFi: RSSI` per device.
- **Temperature (7d)** — `*: Temperature` per device.
- **Energy total (30d)** — `*: Energy total` + `PM1: Energy total`.

### Recreate it

The item patterns and group filter are portable, but recreating requires the
`Shellies` host group to exist. Load via the Zabbix API `dashboard.create` (the
JSON is already shaped for it). Widget field formats are Zabbix 7.4-specific.
