# -*- coding: utf-8 -*-
"""
end_gra.py — END Taguchi / Gri İlişkisel Analiz Scripti
=========================================================
Bu script:
1. Backend'den her sınıfın sensör verilerini çeker
2. Taguchi L9 deney matrisindeki 9 farklı parametre seti için GRA hesaplar
3. En yüksek GRD skorunu "optimal" olarak işaretler
4. Sonuçları POST /api/scenarios/ adresine gönderir
5. Dashboard'daki GRA tablosunu doldurur

KURULUM:
    pip install requests

ÇALIŞTIRMA:
    python end_gra.py
"""

import sys
import io
# Force UTF-8 output so Unicode box-drawing chars work on all Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from datetime import datetime

# ═══════════════════════════════════════════════════════
#   AYARLAR
# ═══════════════════════════════════════════════════════

API_BASE   = "http://localhost:8000"
CLASSROOMS = ["B-201", "B-202", "B-203"]

# ═══════════════════════════════════════════════════════
#   TAGUCHİ L9 DENEY MATRİSİ
#   3 faktör × 3 seviye = 9 deney
#
#   Faktör 1: Işık eşiği (lüks) — ne kadar doğal ışıkta lambayı kıs
#   Faktör 2: AC setpoint (°C)  — klimanın hedef sıcaklığı
#   Faktör 3: CO₂ limiti (ppm)  — havalandırma devreye giriş eşiği
# ═══════════════════════════════════════════════════════

TAGUCHI_L9 = [
    # (senaryo_id,   ışık_eşiği, ac_setpoint, co2_limiti)
    ("deney_1",  450, 21, 800),
    ("deney_2",  450, 22, 1000),
    ("deney_3",  450, 23, 1200),
    ("deney_4",  500, 21, 1000),
    ("deney_5",  500, 22, 1200),   # ← bizim mevcut akıllı sistem ayarı
    ("deney_6",  500, 23, 800),
    ("deney_7",  550, 21, 1200),
    ("deney_8",  550, 22, 800),
    ("deney_9",  550, 23, 1000),
]

# ═══════════════════════════════════════════════════════
#   ADIM 1: BACKEND'DEN VERİ ÇEK
# ═══════════════════════════════════════════════════════

def fetch_sensor_data(classroom_id):
    """
    Backend'den o sınıfın son 37 kayıtını çeker.
    Bu kayıtlar EEM'in gönderdiği gerçek simülasyon verisidir.
    """
    try:
        r = requests.get(
            f"{API_BASE}/api/data/history",
            params={"classroom_id": classroom_id, "limit": 37},
            timeout=5
        )
        if r.status_code == 200:
            return r.json()
        else:
            print(f"  HATA: {classroom_id} verisi alınamadı ({r.status_code})")
            return []
    except Exception as e:
        print(f"  BAĞLANTI HATASI: {e}")
        return []

def fetch_summary(classroom_id):
    """Ortalama enerji ve diğer KPI'ları çeker."""
    try:
        r = requests.get(
            f"{API_BASE}/api/summary/",
            params={"classroom_id": classroom_id},
            timeout=5
        )
        return r.json() if r.status_code == 200 else {}
    except:
        return {}

# ═══════════════════════════════════════════════════════
#   ADIM 2: HER SENARYO İÇİN PERFORMANS HESAPLA
# ═══════════════════════════════════════════════════════

def simulate_scenario(records, isik_esigi, ac_setpoint, co2_limiti):
    """
    Gerçek sensör verilerini alır, farklı parametre setleri
    (ışık eşiği, AC ayarı, CO₂ limiti) ile ne olurdu diye hesaplar.

    Döndürdüğü değerler:
        enerji_ort : Watt cinsinden ortalama güç tüketimi
        lux_ort    : Ortalama ışık seviyesi
        sicaklik_ort: Ortalama iç sıcaklık
        co2_ort    : Ortalama CO₂
    """
    if not records:
        return None

    toplam_enerji = 0
    toplam_lux    = 0
    toplam_sicak  = 0
    toplam_co2    = 0
    sayac         = 0

    for rec in records:
        u    = rec.get("occupancy_u", 0)
        Enat = rec.get("light_natural_lux_E", 0)
        Tout = rec.get("temperature_outdoor", 25)
        co2  = rec.get("co2_ppm", 400)

        if u == 0:
            # Boş sınıf — tüm cihazlar kapalı
            toplam_enerji += 0
            toplam_lux    += Enat
            toplam_sicak  += rec.get("temperature_indoor", 22)
            toplam_co2    += co2
        else:
            # Dolu sınıf — bu senaryonun parametrelerine göre çalıştır

            # Işık: isik_esigi lüks'e kadar doğal ışık yeterliyse lambayı kıs
            x = max(0.0, min(1.0, (isik_esigi - Enat) / 500.0))
            P_lamba = x * 40 * 2   # 2 lamba × 40W
            lux = Enat + x * 500   # x * k * N = x * 250 * 2

            # Klima: setpoint'e göre güç
            fark = abs(Tout - ac_setpoint)
            P_klima = min(900, 300 + 50 * fark)

            # CO₂: limiti aşınca havalandırma devreye giriyor
            # (co2_limiti düşükse daha sık havalandırma = daha az CO₂)
            co2_artis = 3.0 if co2_limiti <= 800 else (4.0 if co2_limiti <= 1000 else 5.0)
            # Basit model: yüksek limitli sistem daha yüksek CO₂'ye izin verir
            co2_sim = min(co2_limiti, co2 * (co2_artis / 3.5))

            toplam_enerji += P_lamba + P_klima
            toplam_lux    += lux
            toplam_sicak  += ac_setpoint + (Tout - ac_setpoint) * 0.03
            toplam_co2    += co2_sim

        sayac += 1

    if sayac == 0:
        return None

    return {
        "enerji_ort":   toplam_enerji / sayac,
        "lux_ort":      toplam_lux    / sayac,
        "sicaklik_ort": toplam_sicak  / sayac,
        "co2_ort":      toplam_co2    / sayac,
    }

# ═══════════════════════════════════════════════════════
#   ADIM 3: GRİ İLİŞKİSEL ANALİZ (GRA)
#
#   Her senaryo için 3 katsayı hesaplanır:
#
#   ξ₁ (Enerji):   Düşük enerji = iyi  → normalize: 1 - (E / E_max)
#   ξ₂ (Işık):     500 lüks'e yakın = iyi → normalize: min(1, lux/500)
#   ξ₃ (Sıcaklık): 22°C'ye yakın = iyi  → normalize: 1 - |T-22|/4
#
#   Katsayı formülü (BM sunumu Sayfa 9):
#       ξ_i(k) = (Δmin + ζ·Δmax) / (Δ₀ᵢ(k) + ζ·Δmax)
#       ζ = 0.5 (ayırt etme katsayısı)
#
#   GRD = (ξ₁ + ξ₂ + ξ₃) / 3
# ═══════════════════════════════════════════════════════

def normalize(degerler, kucuk_iyi=True):
    """
    Ham değerleri 0-1 arasına normalize eder.
    kucuk_iyi=True  → düşük değer daha iyi (enerji gibi)
    kucuk_iyi=False → yüksek değer daha iyi (lüks gibi)
    """
    if not degerler:
        return degerler
    min_d = min(degerler)
    max_d = max(degerler)
    aralik = max_d - min_d

    if aralik == 0:
        return [1.0] * len(degerler)

    if kucuk_iyi:
        return [(max_d - d) / aralik for d in degerler]
    else:
        return [(d - min_d) / aralik for d in degerler]


def gri_katsayi(normalize_deger, zeta=0.5):
    """
    ξ_i(k) = (Δmin + ζ·Δmax) / (Δ₀ᵢ(k) + ζ·Δmax)
    Normalize değer referans dizisine (1.0) olan uzaklıktan hesaplanır.
    """
    delta = abs(1.0 - normalize_deger)   # referans = 1.0 (ideal)
    delta_min = 0.0
    delta_max = 1.0
    return (delta_min + zeta * delta_max) / (delta + zeta * delta_max)


def hesapla_gra(sonuclar):
    """
    Tüm senaryoların performans değerlerini alır,
    normalize eder ve GRD skorlarını döndürür.
    """
    gecerli = [(i, s) for i, s in enumerate(sonuclar) if s is not None]
    if not gecerli:
        return []

    indeksler  = [i for i, _ in gecerli]
    enerjiler  = [s["enerji_ort"]   for _, s in gecerli]
    luxlar     = [s["lux_ort"]      for _, s in gecerli]
    sicakliklar= [s["sicaklik_ort"] for _, s in gecerli]

    # Normalize (enerji: küçük iyi, lüks: büyük iyi, sıcaklık: 22'ye yakın iyi)
    norm_enerji  = normalize(enerjiler,   kucuk_iyi=True)
    norm_lux     = normalize(luxlar,      kucuk_iyi=False)
    # Sıcaklık için 22°C'ye yakınlık → farkı küçük olan iyi
    farklar      = [abs(t - 22) for t in sicakliklar]
    norm_sicaklik= normalize(farklar,     kucuk_iyi=True)

    sonuc = []
    for sira, (idx, _) in enumerate(gecerli):
        xi1 = gri_katsayi(norm_enerji[sira])
        xi2 = gri_katsayi(norm_lux[sira])
        xi3 = gri_katsayi(norm_sicaklik[sira])
        grd = (xi1 + xi2 + xi3) / 3
        sonuc.append({
            "senaryo_idx": idx,
            "xi1": round(xi1, 4),
            "xi2": round(xi2, 4),
            "xi3": round(xi3, 4),
            "grd": round(grd, 4),
        })

    return sonuc

# ═══════════════════════════════════════════════════════
#   ADIM 4: BACKEND'E GÖNDER
# ═══════════════════════════════════════════════════════

def gonder(classroom_id, senaryo_id, xi1, xi2, xi3, grd, optimal):
    payload = {
        "timestamp":        datetime.now().isoformat(),
        "classroom_id":     classroom_id,
        "scenario_id":      senaryo_id,
        "energy_coeff_xi1": xi1,
        "light_coeff_xi2":  xi2,
        "temp_coeff_xi3":   xi3,
        "grd_score_G":      grd,
        "is_optimal":       optimal,
    }
    try:
        r = requests.post(f"{API_BASE}/api/scenarios/", json=payload, timeout=5)
        return r.status_code == 201
    except Exception as e:
        print(f"    GÖNDERME HATASI: {e}")
        return False

# ═══════════════════════════════════════════════════════
#   ANA ÇALIŞMA
# ═══════════════════════════════════════════════════════

def run():
    print("=" * 60)
    print("  END — Taguchi / Gri İlişkisel Analiz")
    print(f"  Backend : {API_BASE}")
    print(f"  Sınıflar: {', '.join(CLASSROOMS)}")
    print(f"  Deney   : {len(TAGUCHI_L9)} senaryo (L9 matrisi)")
    print("=" * 60)

    for classroom_id in CLASSROOMS:
        print(f"\n── {classroom_id} ──────────────────────────────────────")

        # Veri çek
        print("  Sensör verisi çekiliyor...")
        records = fetch_sensor_data(classroom_id)
        if not records:
            print("  Veri bulunamadı — EEM çalışıyor mu?")
            continue
        print(f"  {len(records)} kayıt alındı.")

        # Her senaryo için simüle et
        print("\n  Senaryo simülasyonları:")
        sim_sonuclari = []
        for senaryo_id, isik, ac, co2_lim in TAGUCHI_L9:
            sonuc = simulate_scenario(records, isik, ac, co2_lim)
            sim_sonuclari.append(sonuc)
            if sonuc:
                print(
                    f"    {senaryo_id}: "
                    f"E={sonuc['enerji_ort']:.0f}W  "
                    f"Lux={sonuc['lux_ort']:.0f}  "
                    f"T={sonuc['sicaklik_ort']:.1f}°C  "
                    f"CO₂={sonuc['co2_ort']:.0f}"
                )

        # GRA hesapla
        print("\n  GRA hesaplanıyor...")
        gra_sonuclari = hesapla_gra(sim_sonuclari)

        if not gra_sonuclari:
            print("  GRA hesaplanamadı.")
            continue

        # En yüksek GRD'yi bul
        en_iyi = max(gra_sonuclari, key=lambda x: x["grd"])

        print("\n  Sonuçlar:")
        print(f"  {'Senaryo':<12} {'ξ₁':>6} {'ξ₂':>6} {'ξ₃':>6} {'GRD':>7}  Durum")
        print("  " + "-" * 50)

        for g in gra_sonuclari:
            idx        = g["senaryo_idx"]
            senaryo_id = TAGUCHI_L9[idx][0]
            optimal    = g == en_iyi
            isaret     = "★ EN İYİ" if optimal else ""

            print(
                f"  {senaryo_id:<12} "
                f"{g['xi1']:>6.3f} "
                f"{g['xi2']:>6.3f} "
                f"{g['xi3']:>6.3f} "
                f"{g['grd']:>7.3f}  {isaret}"
            )

            # Backend'e gönder
            ok = gonder(
                classroom_id, senaryo_id,
                g["xi1"], g["xi2"], g["xi3"], g["grd"],
                optimal
            )
            if not ok:
                print(f"    {senaryo_id} gönderilemedi!")

        print(f"\n  Optimal senaryo: {TAGUCHI_L9[en_iyi['senaryo_idx']][0]}"
              f"  (GRD = {en_iyi['grd']:.3f})")

    print("\n" + "=" * 60)
    print("  GRA tamamlandı. Dashboard GRA tablosunu kontrol edin.")
    print("=" * 60)


if __name__ == "__main__":
    run()