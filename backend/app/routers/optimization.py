from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

from app.db.database import get_db
from app.models.schemas import ScenarioCreate

router = APIRouter(prefix="/api/scenarios", tags=["Optimizasyon Sonuçları"])


# ── POST /api/scenarios ─────────────────────────────────────────────────────
@router.post("/", status_code=201, summary="END'den GRA sonucu al")
async def receive_scenario(
    payload: ScenarioCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    END'in Taguchi/GRA hesabı bittiğinde her deney için çağırır.
    is_optimal=True olan kayıt dashboard'da yeşil gösterilir.
    """
    # Eğer bu senaryo "en iyi" olarak işaretlendiyse,
    # aynı classroom için önceki is_optimal kayıtları sıfırla.
    if payload.is_optimal:
        await db.execute(
            """
            UPDATE optimization_results
            SET is_optimal = 0
            WHERE classroom_id = ?
            """,
            (payload.classroom_id,),
        )

    await db.execute(
        """
        INSERT INTO optimization_results (
            timestamp, classroom_id, scenario_id,
            energy_coeff_xi1, light_coeff_xi2, temp_coeff_xi3,
            grd_score_G, is_optimal
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            payload.timestamp.isoformat(),
            payload.classroom_id,
            payload.scenario_id,
            payload.energy_coeff_xi1,
            payload.light_coeff_xi2,
            payload.temp_coeff_xi3,
            payload.grd_score_G,
            int(payload.is_optimal),
        ),
    )
    await db.commit()
    return {"status": "ok", "scenario_id": payload.scenario_id}


# ── GET /api/scenarios ──────────────────────────────────────────────────────
@router.get("/", summary="Tüm deney sonuçlarını listele")
async def list_scenarios(
    classroom_id: str = Query(default="B-204"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Dashboard GRA tablosunu bu endpoint'ten doldurur."""
    rows = await db.execute_fetchall(
        """
        SELECT * FROM optimization_results
        WHERE classroom_id = ?
        ORDER BY grd_score_G DESC
        """,
        (classroom_id,),
    )
    return [dict(r) for r in rows]


# ── GET /api/scenarios/best ─────────────────────────────────────────────────
@router.get("/best", summary="En yüksek GRD skorlu senaryoyu getir")
async def get_best_scenario(
    classroom_id: str = Query(default="B-204"),
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await db.execute_fetchall(
        """
        SELECT * FROM optimization_results
        WHERE classroom_id = ? AND is_optimal = 1
        LIMIT 1
        """,
        (classroom_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Henüz optimal senaryo yok.")
    return dict(rows[0])
