import os
import json
import requests
import firebase_admin

from datetime import datetime
from zoneinfo import ZoneInfo
from firebase_admin import credentials, db


# ==========================================
# KONFIGURASI
# ==========================================

FIREBASE_DATABASE_URL = os.environ["FIREBASE_DATABASE_URL"]
FIREBASE_SERVICE_ACCOUNT = os.environ["FIREBASE_SERVICE_ACCOUNT"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

WAKTU_LOKAL = ZoneInfo("Asia/Jakarta")

BATAS_HARIAN = [4500, 5000]
BATAS_BULANAN = [145000, 150000]


# ==========================================
# KONEKSI FIREBASE
# ==========================================

service_account = json.loads(FIREBASE_SERVICE_ACCOUNT)

if not firebase_admin._apps:
    credential = credentials.Certificate(service_account)
    firebase_admin.initialize_app(
        credential,
        {"databaseURL": FIREBASE_DATABASE_URL}
    )


# ==========================================
# KIRIM TELEGRAM
# ==========================================

def kirim_telegram(pesan):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": pesan
        },
        timeout=20
    )

    response.raise_for_status()

    hasil = response.json()

    if not hasil.get("ok"):
        raise RuntimeError("Pesan Telegram gagal dikirim.")

    print("Pesan Telegram berhasil dikirim.")


# ==========================================
# KONVERSI ANGKA
# ==========================================

def angka(nilai):
    try:
        return float(nilai or 0)
    except (ValueError, TypeError):
        return 0.0


# ==========================================
# MEMBACA FIREBASE
# ==========================================

def baca_data():
    sekarang = datetime.now(WAKTU_LOKAL)

    tanggal = sekarang.strftime("%Y-%m-%d")
    bulan = sekarang.strftime("%Y-%m")

    monitoring = db.reference(
        "AgriWater/WaterMeter/Monitoring"
    ).get()

    riwayat_harian = db.reference(
        f"AgriWater/RiwayatHarian/{tanggal}"
    ).get()

    if monitoring is None:
        raise ValueError("Data Monitoring tidak ditemukan di Firebase.")

    if riwayat_harian is None:
        raise ValueError("Data RiwayatHarian hari ini tidak ditemukan.")

    pemakaian_harian = angka(
        riwayat_harian.get("pemakaianLiter", 0)
    )

    pemakaian_bulanan = angka(
        monitoring.get("monthly_liters", 0)
    )

    peringatan_bocor = monitoring.get("leak_warning", False)

    return {
        "tanggal": tanggal,
        "bulan": bulan,
        "harian": pemakaian_harian,
        "bulanan": pemakaian_bulanan,
        "bocor": peringatan_bocor
    }


# ==========================================
# CEK BATAS PEMAKAIAN
# ==========================================

def cek_dan_kirim(nama, nilai, batas, periode):

    # Setiap batas mempunyai status sendiri
    status_ref = db.reference(
        f"AgriWater/TelegramAlertState/{periode}/{nama}_{batas}"
    )

    sudah_dikirim = status_ref.get() or False

    kondisi = nilai >= batas

    if kondisi and not sudah_dikirim:

        pesan = (
            "PERINGATAN AgriWater\n\n"
            f"{nama.replace('_', ' ').title()}\n"
            f"Pemakaian: {nilai:,.0f} Liter\n"
            f"Batas: {batas:,.0f} Liter\n\n"
            "Mohon periksa penggunaan air."
        )

        kirim_telegram(pesan)
        status_ref.set(True)

        print("Notifikasi terkirim:", nama, batas)

    elif not kondisi and sudah_dikirim:
        status_ref.set(False)
        print("Status notifikasi direset:", nama, batas)


# ==========================================
# CEK KEBOCORAN
# ==========================================

def cek_kebocoran(status):

    bocor = str(status).lower() in [
        "true", "1", "yes", "aktif"
    ]

    status_ref = db.reference(
        "AgriWater/TelegramAlertState/kebocoran"
    )

    sudah_dikirim = status_ref.get() or False

    if bocor and not sudah_dikirim:

        kirim_telegram(
            "PERINGATAN KEBOCORAN AIR!\n\n"
            "Sistem AgriWater mendeteksi indikasi "
            "kebocoran air.\n"
            "Mohon segera periksa instalasi air."
        )

        status_ref.set(True)
        print("Peringatan kebocoran terkirim.")

    elif not bocor and sudah_dikirim:
        status_ref.set(False)
        print("Status kebocoran direset.")


# ==========================================
# PROGRAM UTAMA
# ==========================================

def main():

    data = baca_data()

    print("================================")
    print("MONITORING AgriWater")
    print("Tanggal:", data["tanggal"])
    print("Harian:", data["harian"], "Liter")
    print("Bulanan:", data["bulanan"], "Liter")
    print("Kebocoran:", data["bocor"])
    print("================================")

    # Batas harian
    for batas in BATAS_HARIAN:
        cek_dan_kirim(
            "pemakaian_harian",
            data["harian"],
            batas,
            data["tanggal"]
        )

    # Batas bulanan
    for batas in BATAS_BULANAN:
        cek_dan_kirim(
            "pemakaian_bulanan",
            data["bulanan"],
            batas,
            data["bulan"]
        )

    # Peringatan kebocoran
    cek_kebocoran(data["bocor"])


if __name__ == "__main__":
    main()
