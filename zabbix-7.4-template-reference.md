# Zabbix 7.4 Template Export/Import — Reference

Working notes for authoring importable Zabbix 7.4 template YAML. Source: https://www.zabbix.com/documentation/current/en/manual/xml_export_import/templates Plus **empirical facts verified against a real 7.4 import** (marked ✅ VERIFIED).

> Shelly `sys.reset_reason` codes: the `Shelly reset reason` value map uses Shelly-specific meanings for codes 1,3,4,6,7,8 (4=firmware panic/crash, 7=hardware watchdog, 8=main watchdog — from community reports of Shelly `Sys.GetStatus`) and falls back to the Arduino-ESP32 enum for the rest (5,9–16). Shelly does not publish this enum officially, and the ESP32 table (https://docs.espressif.com/projects/arduino-esp32/en/latest/api/reset_reason.html) disagrees on code 4 (calls it "legacy watchdog"); Shelly meaning preferred where they conflict. Unmapped codes display as the raw number. Treat labels as best-effort.

---

## ⚠️ Gotchas verified the hard way (trust these over the docs)

- ✅ **VERIFIED (7.4):** Value maps must be **template-level** under `templates[].valuemaps:`. A root-level `value_maps:` under `zabbix_export` FAILS import with: `Invalid tag "/zabbix_export": unexpected tag "value_maps".` The general docs imply root-level is allowed — it is NOT accepted by the 7.4 importer. **Always put value maps inside the template as `valuemaps:` (no underscore).**
- ✅ **VERIFIED (7.4):** **Triggers must be at ROOT level** (`zabbix_export.triggers`, 2-space indent, sibling of `templates:`), NOT inside the template. A `triggers:` block inside `templates[]` FAILS with: `Invalid tag "/zabbix_export/templates/template(1)": unexpected tag "triggers".` Root-level triggers still link to their items via the template name in the expression path (`/Template Internal Name/item.key`), so no expression change is needed when relocating. (Same likely applies to `graphs` — root-level, not template child.)
- The importer reports **only the first error**, then stops. Fix, re-import, repeat.
- ✅ **VERIFIED (7.4):** UUIDs must be valid **UUIDv4**, not just 32 hex chars. Import fails with `Invalid parameter "/N/uuid": UUIDv4 is expected.` if the version/variant nibbles are wrong. In the 32-char form: **13th hex digit must be `4`** (version), **17th must be `8/9/a/b`** (variant). Do NOT hand-author UUIDs — generate them: `python3 -c "import uuid;print(uuid.uuid4().hex)"`.
- UUIDs must be exactly **32 lowercase hex chars**, unique across the file. A stray space or extra char = silent-looking parse failure.
- No tabs anywhere. 2-space indent throughout.
- Item-level element referencing a value map is `valuemap:` (singular) with `name:`.

---

## Top-level structure (`zabbix_export`)

```yaml
zabbix_export:
  version: '7.4'
  template_groups:        # REQUIRED — the group(s) templates belong to
    - uuid: <32hex>
      name: Templates/IoT
  host_groups:            # optional — only if host prototypes exist
    - uuid: <32hex>
      name: Shellies
  templates:              # REQUIRED
    - ...
  # NOTE: do NOT put value_maps here at root (see gotcha above).
```

## Template element (`templates[]`)

Valid children (order roughly as below):
```yaml
- uuid: <32hex>
  template: 'Internal Name'      # the reference name used in trigger expressions
  name: 'Display Name'
  description: |
    multi-line text
  vendor:                        # optional
    name: ...
    version: ...
  templates:                     # LINKED (parent) templates — inherit their items/triggers
    - name: 'Base Template Name'
  groups:                        # links to template_groups by name
    - name: Templates/IoT
  macros:
    - ...
  items:
    - ...
  discovery_rules:               # LLD
    - ...
  tags:
    - tag: ...
      value: ...
  dashboards:                    # template-level dashboards
    - ...
  valuemaps:                     # ✅ value maps go HERE, not at root
    - ...
  # NOTE: triggers are NOT a template child — they go at zabbix_export ROOT level.
```

### Linked templates (base + device-specific split)
A child template inherits a base via the `templates:` child block above (referenced by `name`). The base template must be imported FIRST (or in the same batch) or the reference fails to resolve. When splitting one file into two:
- Shared objects (e.g. the `Templates/IoT` template group) MUST use the **same UUID** in both files — otherwise the importer sees a same-name/different-UUID conflict.
- All other UUIDs must be unique across BOTH files.
- Triggers referencing inherited items still use the template that OWNS the item in the expression path (`/Base Template Name/item.key`), not the child.

## Macro element (`macros[]`)

```yaml
- macro: '{$SHELLY.BROKER}'
  value: ''                      # empty default = effectively "required" input
  type: TEXT                     # TEXT | SECRET_TEXT | VAULT (optional, default TEXT)
  description: 'REQUIRED. ...'    # no hard "required" flag exists; use empty+desc
```
There is **no** schema flag that hard-enforces a mandatory macro. Convention: empty `value` + `REQUIRED` in the description. Never hardcode private/site-specific defaults (IP, MAC, device name) — leave blank, fill per host.

## Item element (`items[]`)

```yaml
- uuid: <32hex>
  name: 'PM1: Active power'
  type: ZABBIX_ACTIVE            # see type list below
  key: 'mqtt.get[{$BROKER},{$TOPIC}/status/pm1:0]'
  delay: '0'                     # '0' for active-subscribe / dependent items
  history: '0'                   # optional retention override
  trends: '0'
  value_type: FLOAT              # FLOAT | UNSIGNED | TEXT | CHAR | LOG
  units: W
  master_item:                   # ONLY for type: DEPENDENT
    key: 'mqtt.get[...]'         # must match the master item's key exactly
  preprocessing:
    - type: JSONPATH
      parameters:
        - '$.apower'
  valuemap:                      # singular; references a template valuemap by name
    name: 'Shelly online'
  tags:
    - tag: component
      value: power
```

### item `type` values
`ZABBIX_PASSIVE, TRAP, SIMPLE, INTERNAL, ZABBIX_ACTIVE, EXTERNAL, ODBC, IPMI, SSH, TELNET, CALCULATED, JMX, SNMP_TRAP, DEPENDENT, HTTP_AGENT, SNMP_AGENT, ITEM_TYPE_SCRIPT, ITEM_TYPE_BROWSER`

### item `value_type` values
`FLOAT, UNSIGNED, TEXT, CHAR, LOG`

### preprocessing `type` values (common)
`JSONPATH, BOOL_TO_DECIMAL, MULTIPLIER, RTRIM/LTRIM/TRIM, REGEX, THROTTLE_VALUE, THROTTLE_TIMED_VALUE, JAVASCRIPT, XMLPATH, CSV_TO_JSON, DISCARD_UNCHANGED, DISCARD_UNCHANGED_HEARTBEAT` Params always a list, even if one value: `parameters: ['$.apower']`. Empty-param steps (e.g. BOOL_TO_DECIMAL) still need `parameters: ['']`.

### Master/dependent pattern (read once, reuse)
One `mqtt.get` master item per **topic** (one MQTT subscription). All scalars from that topic = `DEPENDENT` items whose `master_item.key` equals the master's key, each with a `JSONPATH` step. `mqtt.get` subscribes to ONE topic per item, so masters are per-topic; you cannot merge separate topics into one master.

### Agent 2 MQTT named sessions (keep broker/creds off the template)
Define on the AGENT (`zabbix_agent2.conf`), not in Zabbix:
```ini
Plugins.MQTT.Sessions.shelly.Url=tcp://broker.host:1883
Plugins.MQTT.Sessions.shelly.User=
Plugins.MQTT.Sessions.shelly.Password=
Plugins.MQTT.Sessions.shelly.Topic=       # ⚠ DEFAULT ONLY — see below
```
Item key then uses the session NAME as param 1: `mqtt.get[shelly,<full-topic>]`. Benefits: creds live on the agent (not the Zabbix DB); change broker in one place. Template: use a macro like `{$SHELLY.SESSION}` (default the session name) for param 1. ✅ **VERIFIED from plugin source** (`src/go/plugins/mqtt/mqtt.go`, config.go): the session `Topic` field is a **default used only when the item key omits the topic** — it is NOT prepended/concatenated to the item-key topic. So the item key must pass the **FULL** topic path; `{$SHELLY.TOPIC}` holds the whole thing (e.g. `shelly/shelly-livingroom-pm`).

### Discard-unchanged (dedupe near-constant values) — use SPARINGLY
`DISCARD_UNCHANGED` / `DISCARD_UNCHANGED_HEARTBEAT` drop repeated values to save history. Form (heartbeat variant keeps one point per interval so the item doesn't look stale):
```yaml
- type: DISCARD_UNCHANGED_HEARTBEAT
  parameters:
    - '1h'
```
Must be the LAST step (after JSONPATH/BOOL_TO_DECIMAL produce the final value).

⚠️ **Real downsides — usually NOT worth it at small/home scale:**
- Breaks `nodata()`: discarded values look like "no data", so nodata()-based triggers misfire.
- `last()` returns the last *stored* value, which can be misleadingly old.
- Can mask genuine reporting gaps.
The history saved on a few low-rate integer items is negligible; the footguns are not. It earns its keep only at LARGE scale / high poll rates. For a handful of home items,
**just store every value** — simpler and safer. (Decided to remove it from the Shelly
template on this basis, 2026-07-20.) Never put it on metric items that change every reading (power, voltage) — it hides flatlines.

## Trigger element (`zabbix_export.triggers[]` — ROOT level, NOT a template child)

```yaml
- uuid: <32hex>
  expression: 'last(/Internal Name/item.key)>{$MACRO}'   # uses TEMPLATE name
  name: 'Shelly: High active power'
  priority: WARNING             # NOT_CLASSIFIED | INFO | WARNING | AVERAGE | HIGH | DISASTER
  description: '...'
  manual_close: 'YES'           # optional
```
Expressions reference items by the template's `template:` (internal) name — if you rename the template, every expression path must change too.

## Dashboard element (`templates[].dashboards[]`)

⚠️ LEAST CERTAIN part of the schema — widget `fields` naming is fussy and version-sensitive. If import fails here, build the dashboard in the UI instead, or split it into a separate file so the core template imports clean.

```yaml
- uuid: <32hex>
  name: 'Dashboard Name'
  pages:
    - name: Overview
      widgets:
        - type: svggraph           # graph widget
          name: 'Active power'
          x: '0'
          y: '0'
          width: '36'              # grid is 72 columns wide in modern Zabbix
          height: '5'
          fields:
            - type: STRING
              name: 'ds.0.hosts.0.0'
              value: '{HOST.HOST}'
            - type: STRING
              name: 'ds.0.items.0.0'
              value: 'PM1: Active power'   # item display name
            - type: INTEGER
              name: 'ds.0.color.0'
              value: '1'
            - type: STRING
              name: 'time_period.from'
              value: 'now-7d'
            - type: STRING
              name: 'time_period.to'
              value: 'now'
        - type: item               # single value tile
          name: 'Energy total'
          x: '18'
          y: '5'
          width: '9'
          height: '5'
          fields:
            - type: ITEM
              name: 'itemid'
              value:
                host: 'Internal Template Name'
                key: 'shelly.pm1.aenergy.total'
            - type: INTEGER
              name: 'show.1'
              value: '2'
```
Widget field `type` values seen: `STRING, INTEGER, ITEM` (also `ITEM_PROTOTYPE, GRAPH, MAP, HOST_GROUP` for other widget kinds). Item-widget references an item by `{host, key}`; graph-widget data sources reference by host + item display name via the `ds.N.*` field family.

## Value maps (`templates[].valuemaps[]`)  ✅ template-level only

```yaml
valuemaps:
  - uuid: <32hex>
    name: 'Shelly online'
    mappings:
      - value: '0'
        newvalue: 'Offline'
      - value: '1'
        newvalue: 'Online'
```

---

## Pre-import self-check (run before handing over any template)

```python
import re
txt = open('template.yaml').read()
uuids = [u.strip() for u in re.findall(r'uuid:\s*(.+)', txt)]
assert all(re.fullmatch(r'[0-9a-f]{32}', u) for u in uuids), 'bad uuid (not 32 lc hex)'
assert all(u[12]=='4' and u[16] in '89ab' for u in uuids), 'uuid not valid v4 (pos13=4, pos17=8/9/a/b)'
assert len(uuids) == len(set(uuids)), 'dup uuid'
assert '\t' not in txt, 'tab present'
assert not re.search(r'^  value_maps:', txt, re.M), 'value_maps at root — move to template.valuemaps'
assert not re.search(r'^      triggers:', txt, re.M), 'triggers inside template — move to root (2-space) zabbix_export.triggers'
# scan for leaked private data before sharing:
for leak in ['192.168', '<known-mac>', '<device-name>']:
    assert txt.lower().count(leak.lower()) == 0, f'leak: {leak}'
```

Remember: passing this check means the file is *well-formed and clean*, NOT that the 7.4 importer will accept every element. The live import is the only real schema validation — expect to iterate on first-error-only messages.
