"""
run.py - Tek Komutla Tum Sistemi Baslat
"""

import subprocess
import sys
import time
import os
import threading
import requests
import webbrowser

BACKEND_DIR   = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR  = os.path.join(os.path.dirname(BACKEND_DIR), "frontend")
BACKEND_URL   = "http://localhost:8000"
FRONTEND_PORT = 3000
DB_PATH       = os.path.join(BACKEND_DIR, "classroom.db")

surec_listesi = []

def log(baslik, mesaj=""):
    print(f"[{baslik}] {mesaj}")

def backend_hazir_mi():
    try:
        r = requests.get(f"{BACKEND_URL}/", timeout=2)
        return r.status_code == 200
    except:
        return False

def backend_bekle(max_sure=20):
    log("BEKLE", "Backend baslatiliyor...")
    for i in range(max_sure):
        if backend_hazir_mi():
            log("HAZIR", f"Backend {BACKEND_URL} adresinde calisiyor.")
            return True
        time.sleep(1)
    log("HATA", "Backend baslatılamadi!")
    return False

def baslat_arka_plan(komut, isim, calisma_dir=None):
    surec = subprocess.Popen(
        komut,
        cwd=calisma_dir or BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    surec_listesi.append((isim, surec))

    def cikti_oku():
        for satir in surec.stdout:
            satir = satir.rstrip()
            if satir:
                print(f"  [{isim}] {satir}")

    t = threading.Thread(target=cikti_oku, daemon=True)
    t.start()
    return surec

def hepsini_durdur():
    print()
    log("KAPAT", "Tum surecler durduruluyor...")
    for isim, surec in surec_listesi:
        try:
            surec.terminate()
            surec.wait(timeout=3)
            log("OK", f"{isim} durduruldu.")
        except:
            surec.kill()
    log("BITTI", "Sistem kapatildi.")

def main():
    print()
    print("=" * 55)
    print("  Akilli Sinif Otomasyon Sistemi")
    print("  Tek Komut Baslatic")
    print("=" * 55)
    print()

    # -- 1. VERITABANI SIFIRLA --------------------------------
    log("1/5", "Veritabani sifirlanıyor...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        log("OK", "classroom.db silindi.")
    else:
        log("OK", "Veritabani zaten yoktu.")

    # -- 2. BACKEND -------------------------------------------
    log("2/5", "Backend baslatiliyor...")
    backend = baslat_arka_plan(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        "BACKEND"
    )

    if not backend_bekle(max_sure=20):
        hepsini_durdur()
        sys.exit(1)

    # -- 3. FRONTEND ------------------------------------------
    log("3/5", f"Frontend sunucusu baslatiliyor (port {FRONTEND_PORT})...")
    if os.path.exists(FRONTEND_DIR):
        baslat_arka_plan(
            [sys.executable, "-m", "http.server", str(FRONTEND_PORT),
             "--bind", "127.0.0.1"],
            "FRONTEND",
            calisma_dir=FRONTEND_DIR
        )
        time.sleep(1)
        log("HAZIR", f"http://127.0.0.1:{FRONTEND_PORT}/index.html")
    else:
        log("UYARI", f"Frontend klasoru bulunamadi: {FRONTEND_DIR}")

    print()

    # -- 4. EEM — arka planda baslat --------------------------
    log("4/5", "EEM Simulatoru baslatiliyor...")
    eem_script = os.path.join(BACKEND_DIR, "eem_simulator.py")
    if not os.path.exists(eem_script):
        log("HATA", "eem_simulator.py bulunamadi!")
        hepsini_durdur()
        sys.exit(1)

    eem_surec = baslat_arka_plan(
        [sys.executable, eem_script],
        "EEM"
    )

    # Ilk veri gelene kadar bekle, sonra tarayiciyi ac
    log("BEKLE", "Ilk veri bekleniyor...")
    for _ in range(30):
        time.sleep(1)
        try:
            r = requests.get(
                f"{BACKEND_URL}/api/data/latest?classroom_id=B-201",
                timeout=2
            )
            if r.status_code == 200:
                log("OK", "Ilk veri alindi. Tarayici aciliyor...")
                webbrowser.open(f"http://127.0.0.1:{FRONTEND_PORT}/index.html")
                break
        except:
            pass

    # EEM bitene kadar bekle
    eem_surec.wait()
    log("OK", "EEM tamamlandi.")

    # -- 5. GRA -----------------------------------------------
    log("5/5", "GRA Analizi calistiriliyor...")
    gra_script = os.path.join(BACKEND_DIR, "end_gra.py")
    if os.path.exists(gra_script):
        subprocess.run(
            [sys.executable, gra_script],
            cwd=BACKEND_DIR,
            encoding="utf-8",
            errors="replace",
        )
        log("OK", "GRA tamamlandi.")
    else:
        log("UYARI", "end_gra.py bulunamadi, GRA atlandi.")

    # -- SISTEM HAZIR -----------------------------------------
    print()
    print("=" * 55)
    print("  Sistem hazir!")
    print(f"  Dashboard    : http://127.0.0.1:{FRONTEND_PORT}/index.html")
    print(f"  Digital Twin : http://127.0.0.1:{FRONTEND_PORT}/digital_twin.html")
    print(f"  API          : {BACKEND_URL}/docs")
    print()
    print("  Durdurmak icin Ctrl+C")
    print("=" * 55)
    print()

    try:
        while True:
            time.sleep(1)
            if backend.poll() is not None:
                log("HATA", "Backend beklenmedik sekilde durdu!")
                break
    except KeyboardInterrupt:
        pass
    finally:
        hepsini_durdur()


if __name__ == "__main__":
    main()