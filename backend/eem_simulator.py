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

# ── DHT22 capture / datasheet toleransları ─────────────────
DHT22_TEMP_TOLERANCE_C = 0.5
DHT22_HUMIDITY_TOLERANCE_PERCENT = 2.0
TEMP_CAPTURE_WINDOW = 5
TEMP_CAPTURE_ALPHA = 0.35
COMFORT_TEMP_MIN = 20.0
COMFORT_TEMP_MAX = 24.0
AC_SETPOINT = 22.0

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

CAPTURE_STATE = {
    classroom_id: {
        "samples": [],
        "filtered": None,
        "hvac_on": False,
        "indoor_temp": 22.4,
        "humidity": 45.0,
        "co2": 410.0,
        "last_t": None,
    }
    for classroom_id in CLASSROOMS
}

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

def deterministic_sensor_error(classroom_id, t, amplitude):
    """Simülasyonda DHT22 tolerans bandı içinde tekrarlanabilir küçük ölçüm sapması üretir."""
    seed = sum(ord(ch) for ch in classroom_id)
    return amplitude * math.sin((t * 2.7) + seed)

def get_time_delta_hours(classroom_id, t):
    """Bir önceki örnekle mevcut örnek arasındaki simülasyon adımını saat cinsinden döndürür."""
    state = CAPTURE_STATE[classroom_id]
    if state["last_t"] is None:
        dt_hours = 0.25
    else:
        dt_hours = max(0.05, t - state["last_t"])
    state["last_t"] = t
    return dt_hours

def read_and_filter_temperature(classroom_id, true_temperature, t):
    """
    DHT22 sıcaklık capture wrapper'ı.
    Ham okumaya datasheet toleransı kadar sapma ekler, ardından moving average
    ve low-pass filtre ile ani sıçramaları yumuşatır.
    """
    state = CAPTURE_STATE[classroom_id]
    raw_temperature = true_temperature + deterministic_sensor_error(
        classroom_id, t, DHT22_TEMP_TOLERANCE_C
    )

    samples = state["samples"]
    samples.append(raw_temperature)
    if len(samples) > TEMP_CAPTURE_WINDOW:
        samples.pop(0)

    moving_average = sum(samples) / len(samples)
    if state["filtered"] is None:
        filtered = moving_average
    else:
        filtered = (TEMP_CAPTURE_ALPHA * moving_average) + (
            (1.0 - TEMP_CAPTURE_ALPHA) * state["filtered"]
        )
    state["filtered"] = filtered

    return round(raw_temperature, 2), round(filtered, 2)

def read_humidity(classroom_id, occupied, t):
    """DHT22 nem okumasını datasheet tolerans bandıyla simüle eder."""
    state = CAPTURE_STATE[classroom_id]
    base_humidity = state["humidity"] + (8.0 if occupied else 0.0)
    error = deterministic_sensor_error(
        f"{classroom_id}-humidity", t, DHT22_HUMIDITY_TOLERANCE_PERCENT
    )
    return round(max(0.0, min(100.0, base_humidity + error)), 1)

def update_hvac_state(classroom_id, occupied, measured_temperature):
    """
    HVAC aç/kapa kararını ±0.5°C DHT22 toleransına göre ölü bantlı yapar.
    Böylece setpoint çevresinde sık aç/kapa titreşimi oluşmaz.
    """
    state = CAPTURE_STATE[classroom_id]
    if not occupied:
        state["hvac_on"] = False
        return False

    if measured_temperature >= AC_SETPOINT + DHT22_TEMP_TOLERANCE_C:
        state["hvac_on"] = True
    elif measured_temperature <= AC_SETPOINT - DHT22_TEMP_TOLERANCE_C:
        state["hvac_on"] = False
    return state["hvac_on"]

def evolve_co2(classroom_id, occupied, num_students, dt_hours):
    """CO2 seviyesini bir önceki adımdan başlayarak havalandırma ve doluluğa göre evriltir."""
    state = CAPTURE_STATE[classroom_id]
    current_co2 = state["co2"]
    minutes = dt_hours * 60.0

    if occupied:
        co2_gain = num_students * CO2_RATE_PER_PERSON * minutes
        ventilation_pull = 0.18 * (current_co2 - 420.0) * dt_hours
        next_co2 = current_co2 + co2_gain - ventilation_pull
    else:
        empty_decay = 0.65 * (current_co2 - 410.0) * dt_hours
        next_co2 = current_co2 - empty_decay

    state["co2"] = max(400.0, min(2200.0, next_co2))
    return round(state["co2"], 1)

def evolve_indoor_temperature(classroom_id, occupied, num_students, Tout, Enat, dt_hours):
    """
    İç sıcaklığı termal ataletle evriltir.
    Oda sıcaklığı bir önceki değerden başlar; dış hava, güneş kazancı, kişi yükü
    ve HVAC soğutması her adımda yeni sıcaklığa katkı yapar.
    """
    state = CAPTURE_STATE[classroom_id]
    prev_temp = state["indoor_temp"]
    hvac_on = state["hvac_on"]

    envelope_exchange = (Tout - prev_temp) * 0.16 * dt_hours
    people_heat = num_students * 0.028 * dt_hours
    solar_gain = max(0.0, Enat - 250.0) * 0.0022 * dt_hours
    standby_drift = (-0.08 if not occupied else 0.0) * dt_hours

    hvac_cooling = 0.0
    if hvac_on:
        hvac_cooling = (
            1.55
            + 0.022 * num_students
            + 0.035 * max(0.0, Tout - AC_SETPOINT)
        ) * dt_hours

    next_temp = prev_temp + envelope_exchange + people_heat + solar_gain + standby_drift - hvac_cooling
    state["indoor_temp"] = max(17.5, min(39.5, next_temp))
    return state["indoor_temp"]

def evolve_humidity(classroom_id, occupied, num_students, Tout, dt_hours):
    """Nem oranını dış hava etkisi, doluluk ve HVAC kurutmasıyla zaman içinde kaydırır."""
    state = CAPTURE_STATE[classroom_id]
    prev_humidity = state["humidity"]
    outdoor_humidity_target = 54.0 - max(0.0, Tout - 24.0) * 0.75
    target = outdoor_humidity_target + (0.09 * num_students if occupied else -2.0)

    humidity_pull = (target - prev_humidity) * 0.32 * dt_hours
    hvac_drying = 0.0
    if state["hvac_on"]:
        hvac_drying = (2.2 + 0.03 * num_students) * dt_hours

    next_humidity = prev_humidity + humidity_pull - hvac_drying
    state["humidity"] = max(30.0, min(70.0, next_humidity))
    return state["humidity"]

# ═══════════════════════════════════════════════════════
#   AKILLI SİSTEM HESABI  — v2: Dinamik Kişi Sayısı
# ═══════════════════════════════════════════════════════

def compute(classroom_id, t):
    schedule = CLASSROOMS[classroom_id]["schedule"]
    occupied, num_students = get_session(schedule, t)
    dt_hours = get_time_delta_hours(classroom_id, t)

    Enat = E_natural(t)
    Tout = T_outdoor(t)

    # ── Aydınlatma ────────────────────────────────────
    # Yalnızca dolu sınıflarda lambalar yanar.
    x        = max(0.0, min(1.0, (500 - Enat) / (K_LUX * N_LAMPS))) if occupied else 0.0
    P_lights = round(x * P_LAMP * N_LAMPS, 4)
    total_lux= round(Enat + x * K_LUX * N_LAMPS, 2)

    # ── Metabolik Isı Yükü (kişi başı 80 W) ──────────
    #   Q_people = num_students × METABOLIC_HEAT_W
    Q_people = num_students * METABOLIC_HEAT_W   # W

    # HVAC durumu bir önceki filtreli sıcaklıktan karar verir; sonra yeni fizik
    # duruma göre sıcaklık/nem/CO2 bir adım evrilir.
    prior_measured_temp = CAPTURE_STATE[classroom_id]["filtered"]
    if prior_measured_temp is None:
        prior_measured_temp = CAPTURE_STATE[classroom_id]["indoor_temp"]
    hvac_on = update_hvac_state(classroom_id, occupied, prior_measured_temp)

    true_temperature = evolve_indoor_temperature(
        classroom_id, occupied, num_students, Tout, Enat, dt_hours
    )
    evolve_humidity(classroom_id, occupied, num_students, Tout, dt_hours)
    co2 = evolve_co2(classroom_id, occupied, num_students, dt_hours)

    T_raw, T_indoor = read_and_filter_temperature(classroom_id, true_temperature, t)
    humidity = read_humidity(classroom_id, occupied, t)
    hvac_on = update_hvac_state(classroom_id, occupied, T_indoor)

    # ── HVAC Güç Tüketimi ─────────────────────────────
    #   P_ac = P_base + P_dis × |T_dis - T_set| + P_kisi × num_students
    #   HVAC yalnızca ölü bant dışına çıkıldığında devreye girer.
    if hvac_on:
        P_ac = round(
            min(P_AC_MAX,
                P_AC_BASE
                + P_AC_DIŞ * abs(Tout - AC_SETPOINT)
                + P_AC_KİŞİ * num_students),
            2
        )
    else:
        P_ac = 0.0

    return {
        "u":            int(occupied),
        "num_students": num_students,
        "x":            round(x, 4),
        "Enat":         round(Enat, 2),
        "Tout":         round(Tout, 2),
        "T_indoor":     T_indoor,
        "T_raw":        T_raw,
        "humidity":     humidity,
        "temp_tolerance": DHT22_TEMP_TOLERANCE_C,
        "humidity_tolerance": DHT22_HUMIDITY_TOLERANCE_PERCENT,
        "capture_interval_ms": SEND_INTERVAL_SEC * 1000,
        "P_lights":     P_lights,
        "P_ac":         P_ac,
        "Q_people":     round(Q_people, 1),
        "total_lux":    total_lux,
        "total_energy": round(P_lights + P_ac, 2),
        "co2":          round(co2, 1),
        "lighting_ok":  (not occupied) or (total_lux >= 500),
        "thermal_ok":   (not occupied) or (
            COMFORT_TEMP_MIN + DHT22_TEMP_TOLERANCE_C
            <= T_indoor
            <= COMFORT_TEMP_MAX - DHT22_TEMP_TOLERANCE_C
        ),
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
            "temperature_raw":     d["T_raw"],
            "temperature_outdoor": d["Tout"],
            "humidity_percent":    d["humidity"],
            "light_natural_lux_E": d["Enat"],
            "co2_ppm":             int(d["co2"]),
            "temp_tolerance_c":    d["temp_tolerance"],
            "humidity_tolerance_percent": d["humidity_tolerance"],
            "capture_interval_ms": d["capture_interval_ms"],
        },
        "device_status": {
            "ac": {
                "setpoint_temp_Tset": AC_SETPOINT,
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
