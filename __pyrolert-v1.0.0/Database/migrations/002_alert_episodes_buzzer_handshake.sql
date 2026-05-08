-- Migration: add buzzer control and RPi handshake columns to alert_episodes
-- Apply this in Supabase SQL editor

ALTER TABLE alert_episodes ADD COLUMN IF NOT EXISTS buzzer_muted       BOOLEAN   NOT NULL DEFAULT false;
ALTER TABLE alert_episodes ADD COLUMN IF NOT EXISTS buzzer_status      TEXT      NOT NULL DEFAULT 'on';
ALTER TABLE alert_episodes ADD COLUMN IF NOT EXISTS rpi_acknowledged_at TIMESTAMPTZ;
