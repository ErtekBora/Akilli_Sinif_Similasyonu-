"""
eem_simulator.py — EEM Veri Üretici Simülatör (3 Sınıf)
=========================================================
Bu script BM'nin FastAPI backend'ine B-201, B-202 ve B-203 için
aynı anda veri üretir ve gönderir.

NE YAPAR:
    Gerçek bir sınıfta sıcaklık, ışık, CO₂ sensörleri ve klima/lamba
    kontrolcüleri olsaydı ölçülecek olan değerleri matematiksel
    formüllerle hesaplar ve her 5 saniyede backend'e gönderir.

    v2 — Dinamik Doluluk Modeli:
    Her ders saatine num_students (kişi sayısı) eklendi.
    CO₂ birikimi, metabolik ısı yükü ve HVAC tüketimi artık
    gerçek kişi sayısına göre ölçeklenir.

        CO₂  : co2_rate  = num_students × 0.35 ppm/dak
        Isı  : Q_people  = num_students × 80 W  (metabolik yük)
        HVAC : P_ac → Q_people'ı dengeleyecek kadar artar

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
#   3 SINIF TANIMI  — ders programları + kişi sayısı
#
#   Her slot: (baslangic_saat, bitis_saati, num_students)
# ═══════════════════════════════════════════════════════

CLASSROOMS = {
    "B-201": {"schedule": [(8, 10, 40), (11, 13, 35), (14, 16, 38)]},
    "B-202": {"schedule": [(9, 11, 20), (13, 15, 15)]},
    "B-203": {"schedule": [(8,  9,  5), (10, 12, 12), (15, 17,  8)]},
}

API_URL           = "http://localhost:8000/api/data/"
SEND_INTERVAL_SEC = 5

# ── Aydınlatma sabitleri ──────────────────────────────
P_LAMP  = 40.0    # W  (lamba başı nominal güç)
N_LAMPS = 2       # adet
K_LUX   = 250.0   # lüks / lamba

# ── Fiziksel ortam sabitleri ──────────────────────────
CO2_RATE_PER_PERSON  = 0.35   # ppm / dak / kişi
METABOLIC_HEAT_W     = 80.0   # W / kişi  (oturarak orta aktivite)
ROOM_THERMAL_RES     = 0.005  # °C / W    (binanın ısıl direnci — küçük = iyi yalıtım)

# HVAC parametreleri
P_AC_BASE   = 300.0   # W  (kompresör rölanti gücü)
P_AC_DIŞ    = 50.0    # W / °C  (dış-iç fark başına ek güç)
P_AC_KİŞİ   = 5.0     # W / kişi (her kişinin metabolik yükü için ek HVAC)
P_AC_MAX    = 2000.0  # W  (HVAC maksimum kapasitesi — 40 kişi için yükseltildi)

# ═══════════════════════════════════════════════════════
#   YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════

def E_natural(t):
    """Doğal ışık (lüks) — öğlen 650 lx tepe."""
    return max(0.0, 650.0 * math.sin(math.pi * (t - 6.0) / 14.0))

def T_outdoor(t):
    """Dış sıcaklık (°C) — öğleden sonra 34°C tepe."""
    return 18.0 + 16.0 * math.sin(math.pi * (t - 5.0) / 14.0)

def get_session(schedule, t):
    """
    t anındaki oturumu döndürür.
    Dolu ise (True, num_students), boş ise (False, 0) döner.
    """
    for s, e, n in schedule:
        if s <= t < e:
            return True, n
    return False, 0

def minutes_into_session(schedule, t):
    for s, e, n in schedule:
        if s <= t < e:
            return (t - s) * 60.0
    return 0.0

def minutes_since_last_session(schedule, t):
    last_end = None
    for s, e, n in schedule:
        if e <= t:
            last_end = e
    return (t - last_end) * 60.0 if last_end else float('inf')

def students_in_last_session(schedule, t):
    """Biten son oturumdaki kişi sayısını döndürür (CO₂ azalma ölçeği için)."""
    last_n = 0
    for s, e, n in schedule:
        if e <= t:
            last_n = n
    return last_n

# ═══════════════════════════════════════════════════════
#   AKILLI SİSTEM HESABI  — v2: Dinamik Kişi Sayısı
# ═══════════════════════════════════════════════════════

def compute(classroom_id, t):
    schedule = CLASSROOMS[classroom_id]["schedule"]
    occupied, num_students = get_session(schedule, t)

    Enat = E_natural(t)
    Tout = T_outdoor(t)

    # ── Aydınlatma ────────────────────────────────────
    # Yalnızca dolu sınıflarda lambalar yanar.
    x        = max(0.0, min(1.0, (500 - Enat) / (K_LUX * N_LAMPS))) if occupied else 0.0
    P_lights = round(x * P_LAMP * N_LAMPS, 4)
    total_lux= round(Enat + x * K_LUX * N_LAMPS, 2)

    # ── CO₂ Birikimi (kişi sayısına göre ölçeklenir) ──
    #   co2_rate = num_students × CO2_RATE_PER_PERSON  (ppm/dak)
    t_in  = minutes_into_session(schedule, t)
    t_out = minutes_since_last_session(schedule, t)

    if occupied:
        co2_rate = num_students * CO2_RATE_PER_PERSON   # ppm / dak
        # Akıllı havalandırma: 90 dakika sonra bir denge noktasına erişir
        co2 = 400 + co2_rate * min(t_in, 90)
    elif t_out < float('inf'):
        # Sınıf boşaldı — biten oturumdaki kişi sayısına göre başlangıç CO₂'si
        last_n = students_in_last_session(schedule, t)
        co2_peak = 400 + (last_n * CO2_RATE_PER_PERSON) * 90
        co2 = 400 + max(0, (co2_peak - 400) * math.exp(-t_out / 20))
    else:
        co2 = 410.0

    # ── Metabolik Isı Yükü (kişi başı 80 W) ──────────
    #   Q_people = num_students × METABOLIC_HEAT_W
    Q_people = num_students * METABOLIC_HEAT_W   # W

    # ── HVAC Güç Tüketimi ─────────────────────────────
    #   P_ac = P_base + P_dis × |T_dis - 22| + P_kisi × num_students
    #   Klima hem dış sıcaklıkla hem de iç ısı yüküyle mücadele eder.
    if occupied:
        P_ac = round(
            min(P_AC_MAX,
                P_AC_BASE
                + P_AC_DIŞ * abs(Tout - 22)
                + P_AC_KİŞİ * num_students),
            2
        )
    else:
        P_ac = 0.0

    # ── İç Sıcaklık (metabolik yük dahil) ────────────
    #   Dolu: HVAC 22°C'yi tutmaya çalışır, ancak Q_people
    #         yükü küçük bir artışa neden olur.
    #   Formül: T_indoor = 22 + (Q_people - P_ac + P_ac_base) × R_thermal
    #   Basitleştirilmiş: aktif HVAC ile HVAC_KAPASITESI > Q_people ise
    #   sıcaklık 22°C'ye çok yakın, yetersiz kaldığında yükselir.
    if occupied:
        net_heat = Q_people - (P_ac - P_AC_BASE)   # HVAC'ın çektiği ısı hariç net yük
        T_indoor = round(22.0 + max(0.0, net_heat) * ROOM_THERMAL_RES, 2)
    else:
        # Boş sınıf: dış sıcaklığa yavaş yönelir (ısı köprüsü)
        T_indoor = round(15.0 + Tout * 0.35, 2)

    return {
        "u":            int(occupied),
        "num_students": num_students,
        "x":            round(x, 4),
        "Enat":         round(Enat, 2),
        "Tout":         round(Tout, 2),
        "T_indoor":     T_indoor,
        "P_lights":     P_lights,
        "P_ac":         P_ac,
        "Q_people":     round(Q_people, 1),
        "total_lux":    total_lux,
        "total_energy": round(P_lights + P_ac, 2),
        "co2":          round(co2, 1),
        "lighting_ok":  (not occupied) or (total_lux >= 500),
        "thermal_ok":   (not occupied) or (20 <= T_indoor <= 24),
        "co2_ok":       co2 <= 1000,
        "capacity_ok":  0 <= x <= 1,
    }

# ═══════════════════════════════════════════════════════
#   JSON PAYLOAD — BM schemasina birebir uygun
#   + num_students ve Q_people eklendi (yeni alanlar)
# ═══════════════════════════════════════════════════════

def build_payload(classroom_id, t, d):
    h = int(t); m = round((t - h) * 60)
    ts = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)

    return {
        "timestamp":    ts.isoformat(),
        "classroom_id": classroom_id,
        "sensor_data": {
            "occupancy_u":         d["u"],
            "num_students":        d["num_students"],   # ← YENİ: gerçek kişi sayısı
            "temperature_indoor":  d["T_indoor"],
            "temperature_outdoor": d["Tout"],
            "light_natural_lux_E": d["Enat"],
            "co2_ppm":             int(d["co2"]),
        },
        "device_status": {
            "ac": {
                "setpoint_temp_Tset": 22.0,
                "power_w_Pj":        d["P_ac"],
                "metabolic_load_w":  d["Q_people"],     # ← YENİ: metabolik yük bilgisi
            },
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
            "scenario_id":     "beklemede", "energy_coeff_xi1": 0.0,
            "light_coeff_xi2": 0.0,         "temp_coeff_xi3":   0.0,
            "grd_score_G":     0.0,         "is_optimal":       False,
        },
    }

# ═══════════════════════════════════════════════════════
#   ANA DONGU — 3 sinifi ayni adimda gonderir
# ═══════════════════════════════════════════════════════

def run():
    time_steps = [round(8.0 + i * 0.25, 2) for i in range(37)]

    print("=" * 70)
    print("  EEM Simulatoru v2 — Dinamik Kisi Sayisi Modeli")
    print(f"  Backend  : {API_URL}")
    print(f"  Siniflar : {', '.join(CLASSROOMS.keys())}")
    print(f"  Adim     : {len(time_steps)} x 15dk  ({SEND_INTERVAL_SEC}s aralik)")
    print("  CO2 orani: num_students x 0.35 ppm/dak")
    print("  Metab. is: num_students x 80 W")
    print("=" * 70)

    for step, t in enumerate(time_steps, 1):
        h = int(t); m = round((t - h) * 60)
        print(f"\n Adim {step:02d}/37  Saat {h:02d}:{m:02d}")

        for cls_id in CLASSROOMS:
            d = compute(cls_id, t)
            payload = build_payload(cls_id, t, d)

            if d["u"]:
                durum = f"DOLU({d['num_students']:2d}k)"
            else:
                durum = "BOS      "

            kisit = "OK" if all([d["lighting_ok"], d["thermal_ok"],
                                 d["co2_ok"],      d["capacity_ok"]]) else "IHLA"
            print(
                f"  {cls_id}  {durum}  "
                f"lux={d['total_lux']:.0f}  "
                f"T={d['T_indoor']:.1f}C  "
                f"CO2={d['co2']:.0f}  "
                f"HVAC={d['P_ac']:.0f}W  "
                f"Qkisi={d['Q_people']:.0f}W  "
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