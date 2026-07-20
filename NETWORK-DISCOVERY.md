# Network discovery — auto-onboarding Shelly devices (Zabbix 7.4)

This guide sets up **Zabbix network discovery** so new Shelly devices on your IoT network are found by IP and turned into hosts automatically, with the right HTTP template linked.

> Network discovery rules and discovery actions are **server-level configuration**, not part of a template export — so this is a setup guide, not an importable YAML.

## Prerequisites

- The **Zabbix server (or a proxy) must reach the devices over HTTP (TCP/80)**. If your IoT devices are on a separate VLAN, open a rule allowing the Zabbix server to reach the device subnet on port 80 (ICMP/ping is not required). Verify from the server: `python3 -c "import urllib.request;print(urllib.request.urlopen('http://<device-ip>/rpc/Shelly.GetDeviceInfo',timeout=5).read())"`
- Import the HTTP templates first (base + device templates) — see the README.
- The devices expose `/rpc/Shelly.GetDeviceInfo` unauthenticated (`auth_en:false`), which returns `id`, `mac`, `model`, `gen`, `app`. If auth is enabled, discovery needs credentials (out of scope; use the per-host macros instead).

## Step 1 — Discovery rule

**Data collection → Discovery → Create discovery rule**

- **Name:** `Shelly devices`
- **Discovery by:** `Server` (or `Proxy` if a proxy sits inside the device VLAN)
- **IP range:** your IoT range, e.g. `192.0.2.10-200` (use your actual subnet/range, e.g. `192.168.x.10-200`)
- **Update interval:** `1h`
- **Maximum concurrent checks per type:** `Unlimited` (or `One`/`Custom` to throttle scanning if the network is sensitive)
- **Checks:** click **Add** and add an **HTTP** check:
  - Type: `HTTP`, Port: `80`
  - (Zabbix's HTTP discovery check confirms the port responds. It does **not** parse the RPC body — see the limitation below about per-device template selection.)
- **Device uniqueness criteria:** `IP address`
- **Host name:** `DNS name` (recommended — gives readable names from your DNS, e.g. `shellyplus2pm-...`; falls back to `IP address` if no DNS)
- **Visible name:** `Host name` (or `DNS name` / `IP address`)
- **Enabled:** checked

> Zabbix's built-in network-discovery HTTP check only tests connectivity, it does not read the JSON. To key decisions off `model`/`gen`/`app`, use the API-script approach in the "Fully automatic" section below.

## Step 2 — Discovery action

**Alerts → Actions → Discovery actions → Create action**

- **Conditions:**
  - Discovery rule = `Shelly devices`
  - Discovery check = the HTTP check above
  - Discovery status = Up
- **Operations:**
  - Add host
  - Add to host groups: `Shellies`
  - Link to template: **one** of the HTTP device templates (e.g. `Shelly PM Mini Gen3 by HTTP`). The device template pulls in `Shelly Gen2/3 common by HTTP`.

## Step 3 — Per-host macro

The linked template needs `{$SHELLY.HTTP.HOST}` = the device IP. Set it so the auto-created host's discovered IP is used. On the created host, set `{$SHELLY.HTTP.HOST}` to the host's discovered IP (or, if you add an agent/SNMP interface, reference it).

## The honest limitation — mixed device types

Native network discovery **cannot automatically choose the correct device template** per device, because its HTTP check does not read `model`/`app` from `GetDeviceInfo`. So with a single discovery action you either:

- link **only the common base** (`Shelly Gen2/3 common by HTTP`) automatically, and add the device-specific template by hand once per host (knows model at a glance), **or**
- run **separate discovery rules/actions narrowed by IP sub-range** if your device types live in predictable IP blocks, **or**
- use the fully-automatic script below.

## Fully automatic (optional) — API script

For true "device appears → correct template linked", a small external script beats native discovery because it can read `GetDeviceInfo`:

1. Enumerate device IPs (scan the subnet, or read them from your DHCP/mqtt).
2. For each, GET `/rpc/Shelly.GetDeviceInfo` → read `model`/`app`.
3. Map `app` → template:
   - `Mini1G3` → `Shelly Mini 1 Gen3 by HTTP`
   - `Plus2PM` → `Shelly Plus 2PM by HTTP`
   - `PlugSG3` → `Shelly Plug S Gen3 by HTTP`
   - `MiniPMG3` → `Shelly PM Mini Gen3 by HTTP`
4. Call the Zabbix API `host.create` (or `host.update`) with the host, group, template, and `{$SHELLY.HTTP.HOST}` macro set to the IP.
5. (For MQTT hosts instead: GET `/rpc/MQTT.GetConfig`; if `enable=true`, set `{$SHELLY.TOPIC}` from `topic_prefix` and link the MQTT template.)

This script is not included here — it needs a Zabbix API token and is environment-specific. Ask if you want it generated.

## Verify

After discovery runs (or immediately, for a manually created test host):
- **Data collection → Hosts** shows the new host, template linked.
- **Monitoring → Latest data** shows the GetStatus master + dependents populating.
- If empty: confirm the server reaches the device IP over HTTP, and `{$SHELLY.HTTP.HOST}` is set.
