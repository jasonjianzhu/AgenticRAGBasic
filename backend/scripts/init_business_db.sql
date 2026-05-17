-- Mock business database for energy storage systems
-- This script creates tables and populates them with sample data.
-- Data period: 2026-05-27 ~ 2026-06-02 (7 days), hourly time series

-- ============================================================
-- 1. Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    device_name VARCHAR(200) NOT NULL,
    device_model VARCHAR(100) NOT NULL,
    site_name VARCHAR(200) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'running',
    capacity_kwh NUMERIC(10,2),
    rated_power_kw NUMERIC(10,2),
    installed_at TIMESTAMPTZ NOT NULL
);
COMMENT ON TABLE devices IS '站级设备台账(每站1台EMS)';
COMMENT ON COLUMN devices.device_name IS '设备名称';
COMMENT ON COLUMN devices.device_model IS '设备型号';
COMMENT ON COLUMN devices.site_name IS '站点名称';
COMMENT ON COLUMN devices.status IS '运行状态: running/standby/maintenance/offline';
COMMENT ON COLUMN devices.capacity_kwh IS '额定容量(kWh)';
COMMENT ON COLUMN devices.rated_power_kw IS '额定功率(kW)';
COMMENT ON COLUMN devices.installed_at IS '安装时间';

CREATE TABLE IF NOT EXISTS device_metrics (
    id BIGSERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES devices(id),
    metric_name VARCHAR(100) NOT NULL,
    metric_value NUMERIC(12,4) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
COMMENT ON TABLE device_metrics IS '站级运行指标(时序数据,每小时采集)';
COMMENT ON COLUMN device_metrics.metric_name IS '指标名称: soc/soh/power_kw/battery_temp';
COMMENT ON COLUMN device_metrics.metric_value IS '指标值';
COMMENT ON COLUMN device_metrics.recorded_at IS '记录时间';

CREATE INDEX idx_device_metrics_device_time ON device_metrics(device_id, recorded_at);
CREATE INDEX idx_device_metrics_name_time ON device_metrics(metric_name, recorded_at);

CREATE TABLE IF NOT EXISTS alarms (
    id BIGSERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES devices(id),
    alarm_code VARCHAR(20) NOT NULL,
    alarm_level VARCHAR(20) NOT NULL DEFAULT 'warning',
    message TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);
COMMENT ON TABLE alarms IS '告警记录';
COMMENT ON COLUMN alarms.alarm_code IS '告警码: E001-E010';
COMMENT ON COLUMN alarms.alarm_level IS '告警级别: info/warning/critical';
COMMENT ON COLUMN alarms.message IS '告警描述';
COMMENT ON COLUMN alarms.occurred_at IS '发生时间';
COMMENT ON COLUMN alarms.resolved_at IS '解除时间';

CREATE INDEX idx_alarms_device_time ON alarms(device_id, occurred_at);
CREATE INDEX idx_alarms_code ON alarms(alarm_code);

CREATE TABLE IF NOT EXISTS maintenance_logs (
    id BIGSERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES devices(id),
    maintenance_type VARCHAR(50) NOT NULL,
    description TEXT,
    performed_at TIMESTAMPTZ NOT NULL,
    performed_by VARCHAR(100)
);
COMMENT ON TABLE maintenance_logs IS '维护记录';
COMMENT ON COLUMN maintenance_logs.maintenance_type IS '维护类型: inspection/repair/replacement/calibration';
COMMENT ON COLUMN maintenance_logs.description IS '维护描述';
COMMENT ON COLUMN maintenance_logs.performed_at IS '执行时间';
COMMENT ON COLUMN maintenance_logs.performed_by IS '执行人';

CREATE INDEX idx_maintenance_device_time ON maintenance_logs(device_id, performed_at);

CREATE TABLE IF NOT EXISTS site_daily_stats (
    id BIGSERIAL PRIMARY KEY,
    site_name VARCHAR(200) NOT NULL,
    stat_date DATE NOT NULL,
    fault_count INTEGER NOT NULL DEFAULT 0,
    charge_mwh NUMERIC(8,3),
    discharge_mwh NUMERIC(8,3),
    revenue_yuan NUMERIC(10,2),
    UNIQUE(site_name, stat_date)
);
COMMENT ON TABLE site_daily_stats IS '站级日运行统计';
COMMENT ON COLUMN site_daily_stats.site_name IS '站点名称';
COMMENT ON COLUMN site_daily_stats.stat_date IS '统计日期';
COMMENT ON COLUMN site_daily_stats.fault_count IS '当日故障/告警数';
COMMENT ON COLUMN site_daily_stats.charge_mwh IS '日充电量(MWh)';
COMMENT ON COLUMN site_daily_stats.discharge_mwh IS '日放电量(MWh)';
COMMENT ON COLUMN site_daily_stats.revenue_yuan IS '日收益(元)';

CREATE INDEX idx_site_daily_stats_site_date ON site_daily_stats(site_name, stat_date);

-- Create a read-only user for Agent access
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly') THEN
        CREATE ROLE readonly WITH LOGIN PASSWORD 'readonly';
    END IF;
END
$$;
GRANT CONNECT ON DATABASE energy_business TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;

-- ============================================================
-- 2. Mock Data
-- ============================================================

-- Devices: 3 stations, 1 EMS each
INSERT INTO devices (device_name, device_model, site_name, status, capacity_kwh, rated_power_kw, installed_at) VALUES
('EMS-SH-001', 'EMS1000', '上海储能站', 'running', 10000.00, 5000.00, '2025-03-15 08:00:00+08'),
('EMS-BJ-001', 'EMS1000', '北京储能站', 'running', 6000.00, 3000.00, '2025-06-01 08:00:00+08'),
('EMS-GZ-001', 'EMS1000', '广州储能站', 'running', 7000.00, 3500.00, '2025-09-10 08:00:00+08');

-- SOH (hourly, slowly declining)
INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT 1, 'soh', CASE WHEN ts < '2026-05-29+08'::timestamptz THEN 97.50 WHEN ts < '2026-05-31+08'::timestamptz THEN 97.48 WHEN ts < '2026-06-02+08'::timestamptz THEN 97.46 ELSE 97.45 END, ts
FROM generate_series('2026-05-27 00:00:00+08'::timestamptz, '2026-06-02 23:00:00+08'::timestamptz, '1 hour') AS ts;

INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT 2, 'soh', CASE WHEN ts < '2026-05-29+08'::timestamptz THEN 98.20 WHEN ts < '2026-05-31+08'::timestamptz THEN 98.18 WHEN ts < '2026-06-02+08'::timestamptz THEN 98.16 ELSE 98.15 END, ts
FROM generate_series('2026-05-27 00:00:00+08'::timestamptz, '2026-06-02 23:00:00+08'::timestamptz, '1 hour') AS ts;

INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT 3, 'soh', CASE WHEN ts < '2026-05-29+08'::timestamptz THEN 99.00 WHEN ts < '2026-05-31+08'::timestamptz THEN 98.98 WHEN ts < '2026-06-02+08'::timestamptz THEN 98.96 ELSE 98.95 END, ts
FROM generate_series('2026-05-27 00:00:00+08'::timestamptz, '2026-06-02 23:00:00+08'::timestamptz, '1 hour') AS ts;

-- SOC (hourly): charge at night 0-7h, discharge during peak 10-19h
INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT d.id, 'soc',
  ROUND(GREATEST(15, LEAST(95, (
    50 + 40 * SIN((EXTRACT(HOUR FROM ts) - 14) * PI() / 12)
    + (RANDOM() * 6 - 3)
    + CASE WHEN d.id = 2 THEN -3 ELSE 0 END
  )))::numeric, 1),
  ts
FROM devices d
CROSS JOIN generate_series('2026-05-27 00:00:00+08'::timestamptz, '2026-06-02 23:00:00+08'::timestamptz, '1 hour') AS ts;

-- Battery temperature (hourly): 25-42°C, peaks during discharge
INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT d.id, 'battery_temp',
  ROUND((28 + 8 * SIN((EXTRACT(HOUR FROM ts) - 4) * PI() / 12) + (RANDOM() * 3 - 1.5))::numeric, 1),
  ts
FROM devices d
CROSS JOIN generate_series('2026-05-27 00:00:00+08'::timestamptz, '2026-06-02 23:00:00+08'::timestamptz, '1 hour') AS ts;

-- Power (kW, hourly): negative=charge, positive=discharge
INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT d.id, 'power_kw',
  ROUND((CASE
    WHEN EXTRACT(HOUR FROM ts) BETWEEN 0 AND 7 THEN -d.rated_power_kw * (0.6 + RANDOM() * 0.3)
    WHEN EXTRACT(HOUR FROM ts) BETWEEN 10 AND 18 THEN d.rated_power_kw * (0.5 + RANDOM() * 0.4)
    ELSE d.rated_power_kw * (RANDOM() * 0.2 - 0.1)
  END)::numeric, 1),
  ts
FROM devices d
CROSS JOIN generate_series('2026-05-27 00:00:00+08'::timestamptz, '2026-06-02 23:00:00+08'::timestamptz, '1 hour') AS ts;

-- Alarms
INSERT INTO alarms (device_id, alarm_code, alarm_level, message, occurred_at, resolved_at) VALUES
(1, 'E003', 'critical', '电池组温度超过阈值55°C', '2026-05-27 14:23:00+08', '2026-05-27 15:10:00+08'),
(1, 'E005', 'warning', 'SOC低于20%', '2026-05-28 19:15:00+08', '2026-05-28 20:30:00+08'),
(1, 'E007', 'warning', '电压波动超出正常范围', '2026-05-31 16:42:00+08', '2026-05-31 17:15:00+08'),
(1, 'E003', 'critical', '电池过温告警', '2026-06-02 13:40:00+08', '2026-06-02 14:20:00+08'),
(2, 'E002', 'warning', '风扇转速异常', '2026-05-27 10:30:00+08', '2026-05-27 11:20:00+08'),
(2, 'E003', 'critical', '电池温度超过阈值', '2026-05-27 14:50:00+08', '2026-05-27 15:35:00+08'),
(2, 'E004', 'critical', '绝缘电阻低于阈值', '2026-05-29 08:20:00+08', NULL),
(2, 'E005', 'warning', 'SOC过低告警', '2026-05-29 19:05:00+08', '2026-05-29 20:10:00+08'),
(2, 'E003', 'critical', '电池温度超过阈值', '2026-05-29 14:30:00+08', '2026-05-29 15:20:00+08'),
(2, 'E001', 'info', '通信延迟超过500ms', '2026-05-31 09:10:00+08', '2026-05-31 09:25:00+08'),
(2, 'E005', 'warning', 'SOC过低', '2026-05-31 18:45:00+08', '2026-05-31 19:50:00+08'),
(3, 'E003', 'critical', '电池温度超过阈值55°C', '2026-05-28 15:20:00+08', '2026-05-28 16:05:00+08'),
(3, 'E008', 'info', '系统自检完成', '2026-05-30 06:00:00+08', '2026-05-30 06:00:00+08'),
(3, 'E005', 'warning', 'SOC低于20%', '2026-05-31 19:10:00+08', '2026-05-31 20:20:00+08'),
(3, 'E007', 'warning', '电压波动', '2026-06-01 11:35:00+08', '2026-06-01 12:10:00+08');

-- Maintenance logs
INSERT INTO maintenance_logs (device_id, maintenance_type, description, performed_at, performed_by) VALUES
(1, 'inspection', '季度例行巡检，设备运行正常', '2026-05-03 09:00:00+08', '张工'),
(1, 'repair', '更换温度传感器', '2026-05-19 10:00:00+08', '李工'),
(2, 'calibration', 'BMS校准', '2026-05-13 14:00:00+08', '王工'),
(2, 'inspection', '月度巡检', '2026-05-28 09:00:00+08', '王工'),
(2, 'repair', '更换冷却风扇', '2026-05-23 10:00:00+08', '赵工'),
(3, 'inspection', '季度例行巡检', '2026-05-08 09:00:00+08', '陈工'),
(3, 'calibration', '电压传感器校准', '2026-05-21 14:00:00+08', '陈工');

-- Site daily stats
INSERT INTO site_daily_stats (site_name, stat_date, fault_count, charge_mwh, discharge_mwh, revenue_yuan) VALUES
('上海储能站', '2026-05-27', 1, 10.235, 9.724, 5347.20),
('上海储能站', '2026-05-28', 1, 11.082, 10.528, 5790.40),
('上海储能站', '2026-05-29', 0, 9.476, 9.002, 4951.10),
('上海储能站', '2026-05-30', 0, 10.810, 10.270, 5648.50),
('上海储能站', '2026-05-31', 1, 11.520, 10.944, 6019.20),
('上海储能站', '2026-06-01', 0, 10.150, 9.643, 5302.70),
('上海储能站', '2026-06-02', 1, 10.680, 10.146, 5580.30),
('北京储能站', '2026-05-27', 2, 5.124, 4.868, 2433.60),
('北京储能站', '2026-05-28', 0, 5.830, 5.539, 2768.50),
('北京储能站', '2026-05-29', 3, 4.562, 4.334, 2166.00),
('北京储能站', '2026-05-30', 0, 5.480, 5.206, 2602.00),
('北京储能站', '2026-05-31', 2, 6.210, 5.900, 2948.00),
('北京储能站', '2026-06-01', 0, 5.340, 5.073, 2535.50),
('北京储能站', '2026-06-02', 0, 5.650, 5.368, 2682.40),
('广州储能站', '2026-05-27', 0, 7.340, 6.973, 3486.50),
('广州储能站', '2026-05-28', 1, 8.125, 7.719, 3858.50),
('广州储能站', '2026-05-29', 0, 6.850, 6.508, 3252.80),
('广州储能站', '2026-05-30', 0, 7.680, 7.296, 3647.20),
('广州储能站', '2026-05-31', 1, 8.420, 7.999, 3998.50),
('广州储能站', '2026-06-01', 1, 7.150, 6.793, 3395.50),
('广州储能站', '2026-06-02', 0, 7.890, 7.496, 3746.80);
