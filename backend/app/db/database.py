import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../../classroom.db")


async def get_db():
    """Her request için veritabanı bağlantısı döner."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        yield db


async def init_db():
    """Uygulama başlarken tabloları oluşturur."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA synchronous = NORMAL;")
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.executescript("""
            -- 1. Ana sensör/cihaz/kısıt tablosu
            CREATE TABLE IF NOT EXISTS sensor_logs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           DATETIME NOT NULL,
                classroom_id        TEXT     NOT NULL,
                occupancy_u         INTEGER  NOT NULL CHECK (occupancy_u IN (0,1)),
                temperature_indoor  REAL     NOT NULL,
                temperature_outdoor REAL     NOT NULL,
                light_natural_lux_E REAL     NOT NULL,
                co2_ppm             INTEGER  NOT NULL,
                ac_setpoint_temp    REAL     NOT NULL,
                ac_power_w          REAL     NOT NULL,
                total_light_lux     REAL     NOT NULL,
                total_energy_w      REAL     NOT NULL,
                lighting_ok         INTEGER  NOT NULL CHECK (lighting_ok  IN (0,1)),
                thermal_ok          INTEGER  NOT NULL CHECK (thermal_ok   IN (0,1)),
                co2_ok              INTEGER  NOT NULL CHECK (co2_ok       IN (0,1)),
                capacity_ok         INTEGER  NOT NULL CHECK (capacity_ok  IN (0,1))
            );

            -- 2. Bireysel lamba durumları
            CREATE TABLE IF NOT EXISTS light_device_logs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id            INTEGER NOT NULL,
                light_id          TEXT    NOT NULL,
                power_level_x     REAL    NOT NULL,
                nominal_power_w_P REAL    NOT NULL,
                efficiency_k_lux  REAL    NOT NULL,
                actual_power_w    REAL    NOT NULL,
                contributed_lux   REAL    NOT NULL,
                FOREIGN KEY (log_id) REFERENCES sensor_logs(id)
            );

            -- 3. END optimizasyon sonuçları
            CREATE TABLE IF NOT EXISTS optimization_results (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        DATETIME NOT NULL,
                classroom_id     TEXT     NOT NULL,
                scenario_id      TEXT     NOT NULL,
                energy_coeff_xi1 REAL     NOT NULL,
                light_coeff_xi2  REAL     NOT NULL,
                temp_coeff_xi3   REAL     NOT NULL,
                grd_score_G      REAL     NOT NULL,
                is_optimal       INTEGER  NOT NULL CHECK (is_optimal IN (0,1))
            );

            -- 4. Performans indexleri
            CREATE INDEX IF NOT EXISTS idx_sensor_timestamp ON sensor_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_sensor_classroom ON sensor_logs(classroom_id);
            CREATE INDEX IF NOT EXISTS idx_optim_classroom  ON optimization_results(classroom_id);
            CREATE INDEX IF NOT EXISTS idx_light_log_id     ON light_device_logs(log_id);
        """)
        await db.commit()
