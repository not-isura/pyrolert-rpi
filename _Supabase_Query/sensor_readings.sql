-- Create the table
CREATE TABLE sensor_readings (
    id                  BIGSERIAL PRIMARY KEY,
    ts                  BIGINT NOT NULL,
    recorded_at         TIMESTAMPTZ GENERATED ALWAYS AS 
                        (to_timestamp(ts)) STORED,
    gas_co              REAL,
    gas_no2             REAL,
    gas_o2              REAL,
    temp_c              REAL,
    pm25                REAL,
    detection_result    TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX idx_sensor_readings_ts 
ON sensor_readings (ts);

CREATE INDEX idx_sensor_readings_recorded_at 
ON sensor_readings (recorded_at);



-- Allow anyone to read sensor data
CREATE POLICY "allow_public_read"
ON sensor_readings
FOR SELECT
USING (true);

-- Allow anyone to insert sensor data
CREATE POLICY "allow_public_insert"
ON sensor_readings
FOR INSERT
WITH CHECK (true);

-- 1. Drop the generated column first
ALTER TABLE sensor_readings 
DROP COLUMN recorded_at;

-- 2. Change the type of ts
ALTER TABLE sensor_readings 
ALTER COLUMN ts TYPE DOUBLE PRECISION;

-- 3. Recreate the generated column
ALTER TABLE sensor_readings 
ADD COLUMN recorded_at TIMESTAMPTZ 
GENERATED ALWAYS AS (to_timestamp(ts)) STORED;

alter table sensor_readings
add column if not exists temp_roc double precision;