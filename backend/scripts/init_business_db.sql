-- Mock business database for energy storage systems
-- This script creates tables and populates them with sample data.

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
    installed_at TIMESTAMPTZ NOT NULL
);
COMMENT ON TABLE devices IS '设备台账';
COMMENT ON COLUMN devices.device_name IS '设备名称';
COMMENT ON COLUMN devices.device_model IS '设备型号';
COMMENT ON COLUMN devices.site_name IS '站点名称';
COMMENT ON COLUMN devices.status IS '运行状态: running/standby/maintenance/offline';
COMMENT ON COLUMN devices.capacity_kwh IS '额定容量(kWh)';
COMMENT ON COLUMN devices.installed_at IS '安装时间';

CREATE TABLE IF NOT EXISTS device_metrics (
    id BIGSERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES devices(id),
    metric_name VARCHAR(100) NOT NULL,
    metric_value NUMERIC(12,4) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
COMMENT ON TABLE device_metrics IS '设备运行指标(时序数据)';
COMMENT ON COLUMN device_metrics.metric_name IS '指标名称: battery_temp/soc/power_output/voltage/current';
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

-- Devices (6 devices across 3 sites)
INSERT INTO devices (device_name, device_model, site_name, status, capacity_kwh, installed_at) VALUES
('ESS-SH-001', 'ESS-5000', '上海储能站', 'running', 5000.00, '2025-03-15 08:00:00+08'),
('ESS-SH-002', 'ESS-5000', '上海储能站', 'running', 5000.00, '2025-03-15 08:00:00+08'),
('ESS-BJ-001', 'ESS-3000', '北京储能站', 'running', 3000.00, '2025-06-01 08:00:00+08'),
('ESS-BJ-002', 'ESS-3000', '北京储能站', 'maintenance', 3000.00, '2025-06-01 08:00:00+08'),
('ESS-GZ-001', 'ESS-5000', '广州储能站', 'running', 5000.00, '2025-09-10 08:00:00+08'),
('ESS-GZ-002', 'ESS-2000', '广州储能站', 'standby', 2000.00, '2025-09-10 08:00:00+08');

-- Device metrics: generate 7 days of hourly data for each device
-- Battery temperature (25-45°C range)
INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT
    d.id,
    'battery_temp',
    ROUND((30 + 10 * RANDOM() + 5 * SIN(EXTRACT(HOUR FROM ts) * PI() / 12))::numeric, 2),
    ts
FROM devices d
CROSS JOIN generate_series(
    NOW() - INTERVAL '7 days',
    NOW(),
    INTERVAL '1 hour'
) AS ts;

-- SOC (State of Charge, 20-95% range)
INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT
    d.id,
    'soc',
    ROUND((50 + 30 * SIN(EXTRACT(HOUR FROM ts) * PI() / 12) + 10 * RANDOM())::numeric, 2),
    ts
FROM devices d
CROSS JOIN generate_series(
    NOW() - INTERVAL '7 days',
    NOW(),
    INTERVAL '1 hour'
) AS ts;

-- Power output (0-2000 kW range)
INSERT INTO device_metrics (device_id, metric_name, metric_value, recorded_at)
SELECT
    d.id,
    'power_output',
    ROUND((GREATEST(0, 800 + 600 * SIN(EXTRACT(HOUR FROM ts) * PI() / 12) + 200 * RANDOM()))::numeric, 2),
    ts
FROM devices d
CROSS JOIN generate_series(
    NOW() - INTERVAL '7 days',
    NOW(),
    INTERVAL '1 hour'
) AS ts;

-- Alarms: scatter some alarms across the week
INSERT INTO alarms (device_id, alarm_code, alarm_level, message, occurred_at, resolved_at) VALUES
-- 上海站
(1, 'E003', 'critical', '电池组1温度超过阈值60°C', NOW() - INTERVAL '6 days 3 hours', NOW() - INTERVAL '6 days 2 hours'),
(1, 'E003', 'critical', '电池组1温度超过阈值60°C', NOW() - INTERVAL '4 days 14 hours', NOW() - INTERVAL '4 days 13 hours'),
(1, 'E005', 'warning', 'SOC低于20%', NOW() - INTERVAL '5 days 8 hours', NOW() - INTERVAL '5 days 6 hours'),
(2, 'E001', 'info', '通信延迟超过500ms', NOW() - INTERVAL '3 days 10 hours', NOW() - INTERVAL '3 days 9 hours'),
(2, 'E003', 'critical', '电池组2温度超过阈值60°C', NOW() - INTERVAL '2 days 15 hours', NOW() - INTERVAL '2 days 14 hours'),
(2, 'E007', 'warning', '电压波动超出正常范围', NOW() - INTERVAL '1 day 6 hours', NOW() - INTERVAL '1 day 5 hours'),
-- 北京站
(3, 'E002', 'warning', '风扇转速异常', NOW() - INTERVAL '5 days 12 hours', NOW() - INTERVAL '5 days 11 hours'),
(3, 'E003', 'critical', '电池温度超过阈值', NOW() - INTERVAL '3 days 8 hours', NOW() - INTERVAL '3 days 7 hours'),
(3, 'E004', 'critical', '绝缘电阻低于阈值', NOW() - INTERVAL '2 days 16 hours', NULL),
(4, 'E006', 'warning', '充放电循环次数接近上限', NOW() - INTERVAL '6 days 9 hours', NULL),
(4, 'E003', 'critical', '电池温度超过阈值', NOW() - INTERVAL '1 day 11 hours', NOW() - INTERVAL '1 day 10 hours'),
-- 广州站
(5, 'E003', 'critical', '电池温度超过阈值60°C', NOW() - INTERVAL '4 days 13 hours', NOW() - INTERVAL '4 days 12 hours'),
(5, 'E008', 'info', '系统自检完成', NOW() - INTERVAL '2 days 6 hours', NOW() - INTERVAL '2 days 6 hours'),
(5, 'E005', 'warning', 'SOC低于20%', NOW() - INTERVAL '1 day 3 hours', NOW() - INTERVAL '1 day 1 hour'),
(6, 'E001', 'info', '通信延迟', NOW() - INTERVAL '5 days 7 hours', NOW() - INTERVAL '5 days 6 hours'),
(6, 'E009', 'warning', 'BMS通信中断', NOW() - INTERVAL '3 days 14 hours', NOW() - INTERVAL '3 days 12 hours'),
-- Extra alarms for yesterday specifically
(1, 'E003', 'critical', '电池过温告警', NOW() - INTERVAL '1 day 2 hours', NOW() - INTERVAL '1 day 1 hour'),
(3, 'E005', 'warning', 'SOC过低', NOW() - INTERVAL '1 day 8 hours', NOW() - INTERVAL '1 day 7 hours'),
(5, 'E007', 'warning', '电压波动', NOW() - INTERVAL '1 day 16 hours', NOW() - INTERVAL '1 day 15 hours');

-- Maintenance logs
INSERT INTO maintenance_logs (device_id, maintenance_type, description, performed_at, performed_by) VALUES
(1, 'inspection', '季度例行巡检，设备运行正常', NOW() - INTERVAL '30 days', '张工'),
(1, 'repair', '更换温度传感器', NOW() - INTERVAL '15 days', '李工'),
(2, 'inspection', '季度例行巡检', NOW() - INTERVAL '28 days', '张工'),
(3, 'calibration', 'BMS校准', NOW() - INTERVAL '20 days', '王工'),
(3, 'inspection', '月度巡检', NOW() - INTERVAL '5 days', '王工'),
(4, 'repair', '更换冷却风扇', NOW() - INTERVAL '10 days', '赵工'),
(4, 'replacement', '更换电池模组3', NOW() - INTERVAL '3 days', '赵工'),
(5, 'inspection', '季度例行巡检', NOW() - INTERVAL '25 days', '陈工'),
(6, 'calibration', '电压传感器校准', NOW() - INTERVAL '12 days', '陈工');
