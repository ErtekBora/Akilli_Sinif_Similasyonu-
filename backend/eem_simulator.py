"""
eem_simulator.py — EEM Veri Üretici Simülatör (3 Sınıf)
=========================================================
Bu script BM'nin FastAPI backend'ine B-201, B-202 ve B-203 için
aynı anda veri üretir ve gönderir.

NE YAPAR:
    Gerçek bir sınıfta sıcaklık, ışık, CO₂ sensörleri ve klima/lamba
    kontrolcüleri olsaydı ölçülecek olan değerleri matematiksel
    formüllerle hesaplar ve her 5 saniyede backend'e gönderir.

KURULUM:
    pip install requests

ÇALIŞTIRMA:
    python eem_simulator.py
"""

import requests
import time
import math
from datetime import datetime

# ═══════════════════════════════════════════════════════
#   3 SINIF TANIMI  — ders programları buraya
# ═══════════════════════════════════════════════════════

CLASSROOMS = {
    "B-201": {"schedule": [(8, 10), (11, 13), (14, 16)]},
    "B-202": {"schedule": [(9, 11), (13, 15)]},
    "B-203": {"schedule": [(8, 9),  (10, 12), (15, 17)]},
}

API_URL           = "http://localhost:8000/api/data/"
SEND_INTERVAL_SEC = 5

# Fizik sabitleri
P_LAMP  = 40.0
N_LAMPS = 2
K_LUX   = 250.0

# ═══════════════════════════════════════════════════════
#   FİZİK MODELLERİ
# ═══════════════════════════════════════════════════════

def E_natural(t):
    """Doğal ışık (lüks) — öğlen 650 lx tepe."""
    return max(0.0, 650.0 * math.sin(math.pi * (t - 6.0) / 14.0))

def T_outdoor(t):
    """Dış sıcaklık (°C) — öğleden sonra 34°C tepe."""
    return 18.0 + 16.0 * math.sin(math.pi * (t - 5.0) / 14.0)

def is_occupied(schedule, t):
    return any(s <= t < e for s, e in schedule)

def minutes_into_session(schedule, t):
    for s, e in schedule:
        if s <= t < e:
            return (t - s) * 60.0
    return 0.0

def minutes_since_last_session(schedule, t):
    last_end = None
    for s, e in schedule:
        if e <= t:
            last_end = e
    return (t - last_end) * 60.0 if last_end else float('inf')

# ═══════════════════════════════════════════════════════
#   AKILLI SİSTEM HESABI
# ═══════════════════════════════════════════════════════

def compute(classroom_id, t):
    schedule = CLASSROOMS[classroom_id]["schedule"]
    u    = is_occupied(schedule, t)
    Enat = E_natural(t)
    Tout = T_outdoor(t)

    # x_{i,t} = max(0, min(1, (500 - E_nat) / (k_i x N)))
    x         = max(0.0, min(1.0, (500 - Enat) / (K_LUX * N_LAMPS))) if u else 0.0
    P_lights  = round(x * P_LAMP * N_LAMPS, 4)
    total_lux = round(Enat + x * K_LUX * N_LAMPS, 2)

    # P_j(T_set) = min(900, 300 + 50 x |T_dis - 22|)
    P_ac = round(min(900.0, 300 + 50 * abs(Tout - 22)), 2) if u else 0.0

    # CO2 — akilli havalandirma ile yavas artis
    t_in  = minutes_into_session(schedule, t)
    t_out = minutes_since_last_session(schedule, t)
    if u:
        co2 = 400 + 3.0 * min(t_in, 90)
    elif t_out < float('inf'):
        co2 = 400 + max(0, 270 * math.exp(-t_out / 20))
    else:
        co2 = 410.0

    T_indoor = round((22 + (Tout - 22) * 0.03) if u else (15 + Tout * 0.35), 2)

    return {
        "u": int(u), "x": round(x, 4),
        "Enat": round(Enat, 2), "Tout": round(Tout, 2),
        "T_indoor": T_indoor, "P_lights": P_lights, "P_ac": P_ac,
        "total_lux": total_lux, "total_energy": round(P_lights + P_ac, 2),
        "co2": round(co2, 1),
        "lighting_ok": (not u) or (total_lux >= 500),
        "thermal_ok":  (not u) or (20 <= T_indoor <= 24),
        "co2_ok":      co2 <= 1000,
        "capacity_ok": 0 <= x <= 1,
    }

# ═══════════════════════════════════════════════════════
#   JSON PAYLOAD — BM schemasina birebir uygun
# ═══════════════════════════════════════════════════════

def build_payload(classroom_id, t, d):
    h = int(t); m = round((t - h) * 60)
    ts = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)

    return {
        "timestamp":    ts.isoformat(),
        "classroom_id": classroom_id,
        "sensor_data": {
            "occupancy_u":         d["u"],
            "temperature_indoor":  d["T_indoor"],
            "temperature_outdoor": d["Tout"],
            "light_natural_lux_E": d["Enat"],
            "co2_ppm":             int(d["co2"]),
        },
        "device_status": {
            "ac": {"setpoint_temp_Tset": 22.0, "power_w_Pj": d["P_ac"]},
            "lights": [
                {"id": f"L{i+1}", "power_level_x": d["x"],
                 "nominal_power_w_P": P_LAMP, "efficiency_k_lux": K_LUX}
                for i in range(N_LAMPS)
            ],
        },
        "calculated_metrics": {
            "total_light_lux": d["total_lux"],
            "total_energy_w":  d["total_energy"],
        },
        "constraint_status": {
            "lighting_ok": d["lighting_ok"], "thermal_ok": d["thermal_ok"],
            "co2_ok":      d["co2_ok"],      "capacity_ok": d["capacity_ok"],
        },
        "optimization_results": {
            "scenario_id": "beklemede", "energy_coeff_xi1": 0.0,
            "light_coeff_xi2": 0.0,    "temp_coeff_xi3": 0.0,
            "grd_score_G": 0.0,        "is_optimal": False,
        },
    }

# ═══════════════════════════════════════════════════════
#   ANA DONGU — 3 sinifi ayni adimda gonderir
# ═══════════════════════════════════════════════════════

def run():
    time_steps = [round(8.0 + i * 0.25, 2) for i in range(37)]

    print("=" * 65)
    print("  EEM Simulatoru - 3 Sinif Eszamanli")
    print(f"  Backend  : {API_URL}")
    print(f"  Siniflar : {', '.join(CLASSROOMS.keys())}")
    print(f"  Adim     : {len(time_steps)} x 15dk  ({SEND_INTERVAL_SEC}s aralik)")
    print("=" * 65)

    for step, t in enumerate(time_steps, 1):
        h = int(t); m = round((t - h) * 60)
        print(f"\n Adim {step:02d}/37  Saat {h:02d}:{m:02d}")

        for cls_id in CLASSROOMS:
            d = compute(cls_id, t)
            payload = build_payload(cls_id, t, d)

            durum = "DOLU" if d["u"] else "BOS "
            kisit = "OK" if all([d["lighting_ok"], d["thermal_ok"],
                                  d["co2_ok"], d["capacity_ok"]]) else "IHLA"
            print(
                f"  {cls_id}  {durum}  "
                f"lux={d['total_lux']:.0f}  "
                f"T={d['T_indoor']:.1f}C  "
                f"CO2={d['co2']:.0f}  "
                f"E={d['total_energy']:.0f}W  [{kisit}]",
                end="  "
            )

            try:
                r = requests.post(API_URL, json=payload, timeout=5)
                print("-> Gonderildi" if r.status_code == 201 else f"-> HATA {r.status_code}")
            except requests.exceptions.ConnectionError:
                print("-> BACKEND CALISMIYOR")

        if step < len(time_steps):
            time.sleep(SEND_INTERVAL_SEC)

    print("\nSimulasyon tamamlandi - 3 sinif, 37 adim.")

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nDurduruldu.")