# The LoRaWAN Gateway Diagnostic Data (Parquet files)

Each time a LoRaWAN sensor transmits, the Things Network sends BMON a JSON message. BMON
stores the sensor's readings in the [reading database](reading-db.md), and it also keeps
part of the message's radio information for diagnosing signal problems: which gateways
heard the transmission and how strongly. That diagnostic data is described here.

Runnable examples: [`examples/lorawan.sql`](../examples/lorawan.sql) and
[`examples/lorawan.py`](../examples/lorawan.py).

## How it is stored

The data is a directory of [Parquet](https://parquet.apache.org/) files in the BMON
project, one file per day:

```
bmsapp/lora_diagnostics/db/gateway/
    2026-11-17.parquet
    2026-11-18.parquet
    ...
```

- A file holds the records of one **UTC** day, so in Alaska a file starts at 3 pm or 4 pm
  the day before its name.
- BMON adds new records every 5 minutes, and deletes files older than its retention period
  (365 days at the time of writing).
- There is no database server and no locking. Any number of people can query the files at
  once, for as long as they like, without affecting BMON. A file is always replaced as a
  whole, so a query never sees a half-written file.

**One record is one gateway hearing one transmission.** A transmission heard by three
gateways makes three records, identical except for the gateway and signal columns.

## Columns

| Column | Type | Description |
|---|---|---|
| `ts` | timestamp with time zone | When the Things Network received the transmission. |
| `device_eui` | varchar | The unique ID of the sensor device, 16 hex characters in upper case, e.g. `A81758FFFE0526D8`. |
| `device_id` | varchar | The device's ID in the Things Network, e.g. `elt2-a81758fffe071a82`. |
| `application_id` | varchar | The Things Network application the device belongs to. |
| `frm_payload` | varchar | The sensor's raw message, as base64 text. |
| `frame_counter` | integer | The device's count of its transmissions; goes up by one each time (and restarts if the device restarts). Gaps mean transmissions that no gateway heard. |
| `data_rate` | varchar | Spreading factor and bandwidth, e.g. `SF7BW125`. A higher spreading factor (up to SF12) is slower and longer range; devices move to it when the signal is poor. |
| `gateway_id` | varchar | The Things Network ID of the gateway that heard the transmission. |
| `signal_snr` | float | Signal-to-noise ratio at that gateway, dB. Higher is better; below about -10 is marginal. |
| `signal_rssi` | smallint | Received signal strength at that gateway, dBm. Closer to zero is stronger; below about -115 is weak. |

`device_id`, `application_id` and `frm_payload` were added to BMON later than the other
columns, and are NULL in records from before that.

## The `gateway` view

Parquet files can be queried directly by naming them, with `*` standing for all days:

```sql
SELECT count(*)
FROM read_parquet('../bmon/bmsapp/lora_diagnostics/db/gateway/*.parquet');
```

That is a lot to type, so this project defines a **view** named `gateway` that stands for
exactly that expression:

```sql
CREATE OR REPLACE VIEW gateway AS
SELECT * FROM read_parquet('/full/path/to/bmon/bmsapp/lora_diagnostics/db/gateway/*.parquet');
```

and the data can then be queried as if it were one table:

```sql
SELECT gateway_id, count(*) AS records, round(avg(signal_rssi), 1) AS avg_rssi
FROM gateway
WHERE ts >= now() - INTERVAL 1 DAY
GROUP BY gateway_id
ORDER BY records DESC;
```

You don't create the view yourself. It is part of the generated init file `bmon_init.sql`,
so it exists whenever the DuckDB CLI is started with `duckdb -init bmon_init.sql`
(see [duckdb-cli.md](duckdb-cli.md), which also covers `~/.duckdbrc`), and
`bmon_data.connect()` creates it in Python. A view stores no data: every query reads the
current files, including ones BMON has added since you started.

DuckDB only reads the columns a query uses, and skips data outside a `WHERE ts ...`
range, so queries over a year of data are still fast.

## Linking to sensors and buildings

For LoRaWAN sensors, BMON's sensor IDs are the device EUI, an underscore, and the name of
the measurement: `A81758FFFE0526D8_temperature`, `A81758FFFE0526D8_co2`, and so on. So the
part of `sensor_id` before the underscore matches `device_eui` here:

```sql
SELECT DISTINCT g.gateway_id, s.building
FROM gateway AS g
JOIN (
    SELECT DISTINCT split_part(sensor_id, '_', 1) AS device_eui, building FROM sensors
) AS s ON s.device_eui = g.device_eui
ORDER BY g.gateway_id;
```

Gateways have no record in BMON's Django database. BMON itself guesses a gateway's
location as the building of the sensor it hears most strongly.

The data includes every device whose messages are forwarded to BMON, whether or not a
sensor has been set up for it in BMON, so many EUIs may have no match.
