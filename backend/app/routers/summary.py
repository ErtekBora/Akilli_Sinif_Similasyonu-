from fastapi import APIRouter, Depends, Query
import aiosqlite

from app.db.database import get_db
from app.models.schemas import KPISummary

router = APIRouter(prefix="/api/summary", tags=["KPI & Özet"])


@router.get("/", response_model=KPISummary, summary="KPI özet istatistikleri")
async def get_summary(
    classroom_id: str = Query(default="B-204"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Dashboard'un üst kartları için tek sorguda:
    - Ortalama/max/min enerji
    - Ortalama sıcaklık ve CO2
    - Toplam kısıt ihlali sayısı
    - En iyi GRD skoru ve senaryo
    """
    # Sensör istatistikleri
    stat_rows = await db.execute_fetchall(
        """
        SELECT
            COUNT(*)                                    AS record_count,
            ROUND(AVG(total_energy_w), 2)               AS avg_energy_w,
            ROUND(MAX(total_energy_w), 2)               AS max_energy_w,
            ROUND(MIN(total_energy_w), 2)               AS min_energy_w,
            ROUND(AVG(temperature_indoor), 2)           AS avg_temperature,
            ROUND(AVG(co2_ppm), 0)                      AS avg_co2,
            SUM(
                CASE WHEN lighting_ok=0 OR thermal_ok=0
                          OR co2_ok=0  OR capacity_ok=0
                THEN 1 ELSE 0 END
            )                                           AS constraint_violation_count
        FROM sensor_logs
        WHERE classroom_id = ?
        """,
        (classroom_id,),
    )

    stats = dict(stat_rows[0]) if stat_rows else {}

    # En iyi GRD
    opt_rows = await db.execute_fetchall(
        """
        SELECT grd_score_G, scenario_id
        FROM optimization_results
        WHERE classroom_id = ?
        ORDER BY grd_score_G DESC
        LIMIT 1
        """,
        (classroom_id,),
    )
    best = dict(opt_rows[0]) if opt_rows else {}

    return KPISummary(
        classroom_id=classroom_id,
        record_count=stats.get("record_count") or 0,
        avg_energy_w=stats.get("avg_energy_w") or 0.0,
        max_energy_w=stats.get("max_energy_w") or 0.0,
        min_energy_w=stats.get("min_energy_w") or 0.0,
        avg_temperature=stats.get("avg_temperature") or 0.0,
        avg_co2=stats.get("avg_co2") or 0.0,
        constraint_violation_count=stats.get("constraint_violation_count") or 0,
        best_grd_score=best.get("grd_score_G"),
        best_scenario_id=best.get("scenario_id"),
    )