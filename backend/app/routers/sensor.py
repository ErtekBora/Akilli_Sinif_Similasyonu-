from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
import aiosqlite

from app.db.database import get_db
from app.models.schemas import SensorLogCreate, SensorLogResponse

router = APIRouter(prefix="/api/data", tags=["Sensör Verileri"])


# ── POST /api/data ──────────────────────────────────────────────────────────
@router.post("/", status_code=201, summary="EEM'den sensör verisi al")
async def receive_sensor_data(
    payload: SensorLogCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    EEM'in her periyotta (örn. 5 sn) gönderdiği JSON'u alır,
    doğrular ve veritabanına yazar.
    """
    s = payload.sensor_data
    d = payload.device_status
    m = payload.calculated_metrics
    c = payload.constraint_status

    # 1) Ana kayıt — sensor_logs
    cursor = await db.execute(
        """
        INSERT INTO sensor_logs (
            timestamp, classroom_id,
            occupancy_u, temperature_indoor, temperature_outdoor,
            light_natural_lux_E, co2_ppm,
            ac_setpoint_temp, ac_power_w,
            total_light_lux, total_energy_w,
            lighting_ok, thermal_ok, co2_ok, capacity_ok
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payload.timestamp.isoformat(),
            payload.classroom_id,
            s.occupancy_u,
            s.temperature_indoor,
            s.temperature_outdoor,
            s.light_natural_lux_E,
            s.co2_ppm,
            d.ac.setpoint_temp_Tset,
            d.ac.power_w_Pj,
            m.total_light_lux,
            m.total_energy_w,
            int(c.lighting_ok),
            int(c.thermal_ok),
            int(c.co2_ok),
            int(c.capacity_ok),
        ),
    )
    log_id = cursor.lastrowid

    # 2) Bireysel lamba kayıtları — light_device_logs
    for light in d.lights:
        actual_power = round(light.power_level_x * light.nominal_power_w_P, 4)
        contributed_lux = round(light.power_level_x * light.efficiency_k_lux, 4)
        await db.execute(
            """
            INSERT INTO light_device_logs (
                log_id, light_id,
                power_level_x, nominal_power_w_P, efficiency_k_lux,
                actual_power_w, contributed_lux
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                log_id,
                light.id,
                light.power_level_x,
                light.nominal_power_w_P,
                light.efficiency_k_lux,
                actual_power,
                contributed_lux,
            ),
        )

    await db.commit()

    return {
        "status": "ok",
        "log_id": log_id,
        "message": f"Veri kaydedildi. log_id={log_id}",
    }


# ── GET /api/data/latest ────────────────────────────────────────────────────
@router.get("/latest", summary="En son sensör kaydını getir")
async def get_latest(
    classroom_id: str = Query(default="B-204"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Dashboard'un anlık durum kartları için kullanır."""
    row = await db.execute_fetchall(
        """
        SELECT * FROM sensor_logs
        WHERE classroom_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (classroom_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı.")

    record = dict(row[0])

    # Lambalar ayrı tablodan ekleniyor
    lights = await db.execute_fetchall(
        "SELECT * FROM light_device_logs WHERE log_id = ?",
        (record["id"],),
    )
    record["lights"] = [dict(l) for l in lights]

    return record


# ── GET /api/data/history ───────────────────────────────────────────────────
@router.get("/history", response_model=List[SensorLogResponse],
            summary="Zaman aralığı verisi getir")
async def get_history(
    classroom_id: str = Query(default="B-204"),
    limit: int = Query(default=100, le=1000),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Dashboard grafiklerinin zaman serisi için kullanır."""
    rows = await db.execute_fetchall(
        """
        SELECT * FROM sensor_logs
        WHERE classroom_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (classroom_id, limit),
    )
    return [dict(r) for r in rows]
