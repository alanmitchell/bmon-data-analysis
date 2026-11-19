"""Example queries of the LoRaWAN gateway diagnostic data.

Run with:   uv run examples/lorawan.py

The data is described in docs/lorawan-db.md.
"""
import base64

import bmon_data

conn = bmon_data.connect()

# The 'gateway' view presents all of the daily Parquet files as one table.
print("Period covered by the data:")
conn.sql("SELECT count(*) AS record_count, min(ts) AS first, max(ts) AS last FROM gateway").show()

# --- Signal quality of each gateway, as a DataFrame.
gateways = conn.sql("""
    SELECT
        gateway_id,
        count(*) AS record_count,
        count(DISTINCT device_eui) AS device_count,
        round(avg(signal_rssi), 1) AS avg_rssi,
        round(avg(signal_snr), 1) AS avg_snr,
        max(ts) AS last_heard
    FROM gateway
    GROUP BY gateway_id
    ORDER BY record_count DESC
""").df()
print(f"{len(gateways)} gateways. The busiest:")
print(gateways.head(10))

# --- One device: hourly signal strength at each gateway that hears it.
eui = conn.sql(
    "SELECT device_eui FROM gateway GROUP BY device_eui ORDER BY count(DISTINCT gateway_id) DESC LIMIT 1"
).fetchall()[0][0]
print(f"\nHourly average RSSI of device {eui} at each gateway:")
hourly = conn.sql("""
    SELECT date_trunc('hour', ts) AS hour, gateway_id, avg(signal_rssi) AS avg_rssi
    FROM gateway
    WHERE device_eui = ?
    GROUP BY hour, gateway_id
    ORDER BY hour
""", params=[eui]).df()
print(hourly.pivot(index="hour", columns="gateway_id", values="avg_rssi").round(1).tail())

# --- The payload is the sensor's raw message as base64 text. It is NULL in
# records stored before BMON started saving it.
rows = conn.sql("""
    SELECT device_eui, device_id, application_id, frm_payload
    FROM gateway
    WHERE frm_payload IS NOT NULL
    ORDER BY ts DESC
    LIMIT 1
""").fetchall()
if rows:
    device_eui, device_id, application_id, payload = rows[0]
    print(f"\nLatest payload, from {device_id} in application {application_id}:")
    print(f"  base64: {payload}   hex: {base64.b64decode(payload).hex()}")

# --- Join to the Django database to name the buildings a gateway serves.
# The first part of a LoRaWAN sensor_id (before the '_') is the device EUI.
by_building = conn.sql("""
    SELECT g.gateway_id, s.building, count(DISTINCT g.device_eui) AS device_count
    FROM gateway AS g
    JOIN (
        SELECT DISTINCT split_part(sensor_id, '_', 1) AS device_eui, building FROM sensors
    ) AS s ON s.device_eui = g.device_eui
    GROUP BY g.gateway_id, s.building
    ORDER BY g.gateway_id, device_count DESC
""").df()
print(f"\nGateway / building combinations found: {len(by_building)}")
print(by_building.head(10))
