-- Example queries of the LoRaWAN gateway diagnostic data.
-- The data is described in docs/lorawan-db.md.
--
-- Start the DuckDB CLI with:   duckdb -init bmon_init.sql
-- then paste queries from this file, or run the whole file with:
--     .read examples/lorawan.sql

-- The columns of the data, and the period it covers.
DESCRIBE gateway;
SELECT count(*) AS record_count, min(ts) AS first_record, max(ts) AS last_record FROM gateway;

-- The busiest gateways: records relayed, number of different sensors heard,
-- and average signal strength.
SELECT
    gateway_id,
    count(*) AS record_count,
    count(DISTINCT device_eui) AS device_count,
    round(avg(signal_rssi), 1) AS avg_rssi,
    round(avg(signal_snr), 1) AS avg_snr
FROM gateway
GROUP BY gateway_id
ORDER BY record_count DESC
LIMIT 15;

-- Gateways that have been silent for more than 6 hours (measured from the
-- newest record in the data, so the query also works on an old copy).
SELECT gateway_id, max(ts) AS last_heard, (SELECT max(ts) FROM gateway) - max(ts) AS silent_for
FROM gateway
GROUP BY gateway_id
HAVING silent_for > INTERVAL 6 HOUR
ORDER BY silent_for DESC;

-- The weakest sensors: for each device, its best gateway's average signal.
-- Devices where even the best gateway is weak are at risk of losing readings.
WITH by_gateway AS (
    SELECT device_eui, gateway_id, avg(signal_rssi) AS avg_rssi, avg(signal_snr) AS avg_snr, count(*) AS n
    FROM gateway
    GROUP BY device_eui, gateway_id
)
SELECT
    device_eui,
    arg_max(gateway_id, avg_rssi) AS best_gateway,
    round(max(avg_rssi), 1) AS best_avg_rssi,
    count(*) AS gateways_heard_by
FROM by_gateway
GROUP BY device_eui
ORDER BY best_avg_rssi
LIMIT 15;

-- Missed transmissions for one device. Each transmission has a frame_counter
-- one higher than the last, so a gap in the counter is a transmission that no
-- gateway received. (A transmission heard by 3 gateways makes 3 records. The
-- result is wrong if the device restarted, because its counter starts over.)
SET VARIABLE eui = (SELECT device_eui FROM gateway GROUP BY device_eui ORDER BY count(*) DESC LIMIT 1);
WITH frames AS (
    SELECT DISTINCT frame_counter FROM gateway WHERE device_eui = getvariable('eui')
)
SELECT
    getvariable('eui') AS device_eui,
    count(*) AS frames_received,
    max(frame_counter) - min(frame_counter) + 1 AS frames_sent,
    round(100.0 * (1 - count(*) / (max(frame_counter) - min(frame_counter) + 1)), 1) AS pct_missed
FROM frames;

-- Use of each data rate (spreading factor). High spreading factors (SF10+)
-- mean the sensor is struggling to reach a gateway.
SELECT data_rate, count(DISTINCT device_eui) AS device_count, count(*) AS record_count
FROM gateway
GROUP BY data_rate
ORDER BY data_rate;

-- Join to the Django database: which buildings' sensors does each gateway hear?
-- The first part of a LoRaWAN sensor_id (before the '_') is the device EUI.
SELECT
    g.gateway_id,
    s.building,
    count(DISTINCT g.device_eui) AS device_count,
    round(avg(g.signal_rssi), 1) AS avg_rssi
FROM gateway AS g
JOIN (
    SELECT DISTINCT split_part(sensor_id, '_', 1) AS device_eui, building FROM sensors
) AS s ON s.device_eui = g.device_eui
GROUP BY g.gateway_id, s.building
ORDER BY g.gateway_id, device_count DESC;
