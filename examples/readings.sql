-- Example queries of the sensor reading database.
-- Its structure is described in docs/reading-db.md.
--
-- Start the DuckDB CLI with:   duckdb -init bmon_init.sql
-- then paste queries from this file, or run the whole file with:
--     .read examples/readings.sql

-- Sensor IDs differ between BMON installations, so these examples use a
-- variable. Here it is set to the first temperature sensor found; set it to a
-- sensor of your own with, for example:
--     SET VARIABLE sid = 'A81758FFFE0526D8_temperature';
-- (Look sensor IDs up with:  SELECT * FROM sensors WHERE building ILIKE '%name%';)
-- A sensor that has never reported has no table in the reading database, and
-- readings() fails for it; the second condition below leaves those out.
SET VARIABLE sid = (
    SELECT sensor_id FROM sensors
    WHERE sensor ILIKE '%temperature%'
      AND sensor_id IN (SELECT table_name FROM duckdb_tables() WHERE database_name = 'rd')
    ORDER BY sensor_id LIMIT 1
);
SELECT building, sensor, sensor_id, unit FROM sensors WHERE sensor_id = getvariable('sid');

-- How much data does the sensor have, and over what period?
SELECT count(*) AS reading_count, min(ts) AS first_reading, max(ts) AS last_reading
FROM readings(getvariable('sid'));

-- The 10 most recent readings.
SELECT ts, val
FROM readings(getvariable('sid'))
ORDER BY ts DESC
LIMIT 10;

-- Daily average, minimum and maximum for the sensor's last 30 days of data.
SELECT
    date_trunc('day', ts)::DATE AS day,
    round(avg(val), 2) AS average,
    min(val) AS minimum,
    max(val) AS maximum,
    count(*) AS reading_count
FROM readings(getvariable('sid'))
WHERE ts >= (SELECT max(ts) FROM readings(getvariable('sid'))) - INTERVAL 30 DAY
GROUP BY day
ORDER BY day;

-- Readings in a date range (change the dates to a period your sensor has data
-- for). Dates without a time zone are in the session's
-- time zone, which is your computer's unless you change it, for example:
--     SET TimeZone = 'America/Anchorage';
SELECT ts, val
FROM readings(getvariable('sid'))
WHERE ts >= '2024-01-01' AND ts < '2024-01-02'
ORDER BY ts;

-- Average value for each hour of the day (0 - 23).
SELECT hour(ts) AS hour_of_day, round(avg(val), 2) AS average, count(*) AS reading_count
FROM readings(getvariable('sid'))
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- The raw table can also be queried directly. The table name is the sensor ID
-- and must be in double quotes; 'ts' is then a Unix timestamp (seconds).
--     SELECT ts, to_timestamp(ts) AS time, val FROM rd."A81758FFFE0526D8_temperature" LIMIT 5;

-- The most recent alerts that BMON sent.
SELECT ts, building, sensor_id, message
FROM alert_log
ORDER BY ts DESC
LIMIT 10;
