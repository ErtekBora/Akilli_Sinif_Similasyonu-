from pydantic import BaseModel, Field, field_validator
from typing import List
from datetime import datetime


# ── Lamba ──────────────────────────────────────────────────────────────────
class LightDevice(BaseModel):
    id: str                                          # "L1", "L2"
    power_level_x: float = Field(ge=0.0, le=1.0)   # x_i,t ∈ [0,1]
    nominal_power_w_P: float = Field(gt=0)          # P_i
    efficiency_k_lux: float = Field(gt=0)           # k_i


# ── AC ─────────────────────────────────────────────────────────────────────
class ACDevice(BaseModel):
    setpoint_temp_Tset: float   # T_set,t
    power_w_Pj: float           # P_j(T_set,t)


# ── Cihaz Durumu ───────────────────────────────────────────────────────────
class DeviceStatus(BaseModel):
    ac: ACDevice
    lights: List[LightDevice]


# ── Sensör Verisi ──────────────────────────────────────────────────────────
class SensorData(BaseModel):
    occupancy_u: int = Field(ge=0, le=1)     # u_t ∈ {0,1}
    temperature_indoor: float                 # T_indoor,t
    temperature_outdoor: float                # dış sıcaklık
    light_natural_lux_E: float = Field(ge=0) # E_natural,t
    co2_ppm: int = Field(ge=0)               # CO2,t


# ── Hesaplanan Metrikler ───────────────────────────────────────────────────
class CalculatedMetrics(BaseModel):
    total_light_lux: float   # Σ(x_i,t * k_i) + E_natural
    total_energy_w: float    # Σ(P_i * x_i,t) + P_j


# ── Kısıt Durumu ──────────────────────────────────────────────────────────
class ConstraintStatus(BaseModel):
    lighting_ok: bool   # Σ(x*k) + E_nat ≥ 500*u_t
    thermal_ok: bool    # 20 ≤ T_indoor ≤ 24 (doluyken)
    co2_ok: bool        # CO2 ≤ 1000 ppm
    capacity_ok: bool   # 0 ≤ x_i,t ≤ 1


# ── Optimizasyon Sonucu ────────────────────────────────────────────────────
class OptimizationResult(BaseModel):
    scenario_id: str
    energy_coeff_xi1: float = Field(ge=0, le=1)
    light_coeff_xi2: float  = Field(ge=0, le=1)
    temp_coeff_xi3: float   = Field(ge=0, le=1)
    grd_score_G: float      = Field(ge=0, le=1)
    is_optimal: bool


# ── EEM'den Gelen Ana JSON (POST /api/data) ────────────────────────────────
class SensorLogCreate(BaseModel):
    timestamp: datetime
    classroom_id: str
    sensor_data: SensorData
    device_status: DeviceStatus
    calculated_metrics: CalculatedMetrics
    constraint_status: ConstraintStatus
    optimization_results: OptimizationResult

    @field_validator("calculated_metrics")
    @classmethod
    def validate_metrics(cls, v: CalculatedMetrics, info) -> CalculatedMetrics:
        """Backend, EEM'in gönderdiği toplam enerji değerini çapraz kontrol eder."""
        # Validasyon için device_status gerekli; henüz parse edilmemişse atla
        data = info.data
        if "device_status" not in data:
            return v

        ds: DeviceStatus = data["device_status"]
        expected_energy = round(
            sum(l.power_level_x * l.nominal_power_w_P for l in ds.lights)
            + ds.ac.power_w_Pj,
            2,
        )
        if abs(v.total_energy_w - expected_energy) > 1.0:   # 1 W tolerans
            raise ValueError(
                f"total_energy_w uyuşmuyor: gönderilen={v.total_energy_w}, "
                f"hesaplanan={expected_energy}"
            )
        return v


# ── END'den Gelen Optimizasyon Kaydı (POST /api/scenarios) ────────────────
class ScenarioCreate(BaseModel):
    timestamp: datetime
    classroom_id: str
    scenario_id: str
    energy_coeff_xi1: float = Field(ge=0, le=1)
    light_coeff_xi2: float  = Field(ge=0, le=1)
    temp_coeff_xi3: float   = Field(ge=0, le=1)
    grd_score_G: float      = Field(ge=0, le=1)
    is_optimal: bool


# ── Response Modelleri ─────────────────────────────────────────────────────
class SensorLogResponse(BaseModel):
    id: int
    timestamp: str
    classroom_id: str
    occupancy_u: int
    temperature_indoor: float
    temperature_outdoor: float
    light_natural_lux_E: float
    co2_ppm: int
    ac_setpoint_temp: float
    ac_power_w: float
    total_light_lux: float
    total_energy_w: float
    lighting_ok: bool
    thermal_ok: bool
    co2_ok: bool
    capacity_ok: bool


class KPISummary(BaseModel):
    classroom_id: str
    record_count: int
    avg_energy_w: float
    max_energy_w: float
    min_energy_w: float
    avg_temperature: float
    avg_co2: float
    constraint_violation_count: int   # Herhangi bir kısıt ihlali olan kayıt sayısı
    best_grd_score: float | None
    best_scenario_id: str | None
