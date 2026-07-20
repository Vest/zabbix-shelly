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

**Alerts → Actions → Discovery actions → Create action.** The dialog has two tabs: **Action** (name + conditions) and **Operations**.

### Action tab

- **Name:** `Shelly devices`
- **Conditions:** click **Add**. In the *New condition* dialog:
  - **Type:** `Discovery rule`, **Operator:** `equals`, **Discovery rules:** select `Shelly devices` (the rule from Step 1)
  - **Add a second condition to match only Shelly-named devices** (a name-prefix filter): **Type:** `Host name`, **Operator:** `matches`, **value:** `^shelly` (regex). This acts on the **discovered DNS name**, so only devices whose DNS name starts with `shelly` (e.g. `shellyplus2pm-...`, `shelly1minig3-...`) get a host created — everything else that answers on port 80 is ignored. Use `contains` `shelly` for a looser match.
  - With two conditions, set the **Calculation** to `And/Or` (or `And`) so both must match.
- **Enabled:** checked

> Requirements for the name filter: your DNS must resolve the device names (e.g. via Dnsmasq/DHCP, which names Shellies `shelly<model>-<mac>`), AND the discovery rule's **Host name** source must be `DNS name` (Step 1). If DNS doesn't resolve them, the discovered name is the IP and `^shelly` won't match — fall back to narrowing the rule's IP range instead.

> There is no way to filter by device model/gen here: the `Received value` condition type only has data for checks that return a value (Zabbix agent, SNMP) — the plain HTTP port check does not capture the response body, so it can't match on `"gen":3` or model. Selecting the right per-device template is handled by the approaches in "The honest limitation" / "Fully automatic" below.

### Operations tab

At least one operation is required (the Action tab warns *"At least one operation must exist"*). Click **Add** under Operations; each opens *Operation details* with an **Operation** dropdown. Add these (exact dropdown names):

- **Add host**
- **Add to host group** → `Shellies`
- **Link template** → one of the HTTP device templates (e.g. `Shelly PM Mini Gen3 by HTTP`). It pulls in `Shelly Gen2 Gen3 common by HTTP` automatically.
- **Set host inventory mode** → `Automatic` (optional but recommended — makes the MAC/IP/Vendor/Model items auto-populate host inventory without touching each host by hand).

> Because the built-in discovery check can't read the device model, a single action links one fixed template to everything it matches. See "The honest limitation" and "Fully automatic" below for handling mixed device types.

## Step 3 — Device address (no macro needed)

The HTTP template's master item URL uses **`{HOST.CONN}`**, which resolves to the host interface's address — either its **IP** or **DNS name**, depending on the interface's **Connect to** setting. Network discovery creates the host with an agent interface carrying the discovered IP and DNS name, so this works with **no per-host macro**. Set **Connect to = DNS** on the interface to poll by hostname (robust if the DHCP IP changes, given your DNS resolves the device names); leave it on **IP** to pin the address. Either works — the Shelly responds on both.

## The honest limitation — mixed device types

Native network discovery **cannot automatically choose the correct device template** per device, because its HTTP check does not read `model`/`app` from `GetDeviceInfo`. So with a single discovery action you either:

- link **only the common base** (`Shelly Gen2 Gen3 common by HTTP`) automatically, and add the device-specific template by hand once per host (knows model at a glance), **or**
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
4. Call the Zabbix API `host.create` (or `host.update`) with the host, group, template, and an agent **interface** set to the device IP/DNS (the template URL uses `{HOST.CONN}` — no macro needed).
5. (For MQTT hosts instead: GET `/rpc/MQTT.GetConfig`; if `enable=true`, set `{$SHELLY.TOPIC}` from `topic_prefix` and link the MQTT template.)

This script is not included here — it needs a Zabbix API token and is environment-specific. Ask if you want it generated.

## Verify

After discovery runs (or immediately, for a manually created test host):
- **Data collection → Hosts** shows the new host, template linked.
- **Monitoring → Latest data** shows the GetStatus master + dependents populating.
- If empty: confirm the server reaches the device over HTTP, and the host has an interface with the device IP/DNS (the URL uses `{HOST.CONN}`; a missing interface makes it `http:///rpc/...` → `Could not resolve host: rpc`).
