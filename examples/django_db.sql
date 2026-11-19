-- Example queries of the Django database (buildings, sensors, alerts ...).
-- Table descriptions are in docs/django-db.md.
--
-- Start the DuckDB CLI with:   duckdb -init bmon_init.sql
-- then paste queries from this file, or run the whole file with:
--     .read examples/django_db.sql

-- All of the buildings.
SELECT id, title, latitude, longitude, timezone
FROM bmon.bmsapp_building
ORDER BY title;

-- The number of sensors in each building, using the 'sensors' view.
SELECT building, count(*) AS sensor_count
FROM sensors
GROUP BY building
ORDER BY sensor_count DESC;

-- Find sensors by words in the building or sensor title (ILIKE ignores case).
SELECT building, sensor_group, sensor, sensor_id, unit
FROM sensors
WHERE sensor ILIKE '%temperature%'
ORDER BY building, sensor
LIMIT 20;

-- Sensors that are not assigned to any building.
SELECT sen.sensor_id, sen.title
FROM bmon.bmsapp_sensor AS sen
LEFT JOIN bmon.bmsapp_bldgtosensor AS b2s ON b2s.sensor_id = sen.id
WHERE b2s.id IS NULL
ORDER BY sen.sensor_id;

-- The alert conditions that are set up, with the sensor each one watches.
SELECT
    sen.sensor_id,
    sen.title AS sensor,
    alert.condition,
    alert.test_value,
    alert.active::BOOLEAN AS active,
    to_timestamp(alert.last_notified) AS last_notified
FROM bmon.bmsapp_alertcondition AS alert
JOIN bmon.bmsapp_sensor AS sen ON alert.sensor_id = sen.id
ORDER BY sen.sensor_id;

-- The buildings of each organization (a many-to-many link table).
SELECT org.title AS organization, bldg.title AS building
FROM bmon.bmsapp_organization AS org
JOIN bmon.bmsapp_organization_buildings AS link ON link.organization_id = org.id
JOIN bmon.bmsapp_building AS bldg ON link.building_id = bldg.id
ORDER BY organization, building;
