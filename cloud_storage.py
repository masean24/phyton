"""
Cloud Storage — Simpan link ke Google Sheets
Semua PC yang jalanin bot bisa append ke spreadsheet yang sama.

Setup:
  1. pip install gspread google-auth
  2. Buat Service Account di Google Cloud Console
  3. Download credentials.json → taruh di folder ini
  4. Buat Google Spreadsheet → Share ke email service account
  5. Copy Spreadsheet ID → paste di SPREADSHEET_ID

Dokumentasi lengkap: baca TUTORIAL.md
"""

import os
import sys
import threading
from datetime import datetime
from typing import Optional, List

try:
    import gspread
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
#  CONFIG — ISI SESUAI PUNYAMU
# ═══════════════════════════════════════════════════════════════

# Path ke service account JSON (default: credentials.json di folder ini)
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

# Spreadsheet ID dari URL Google Sheets
# Contoh URL: https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ/edit
# Maka SPREADSHEET_ID = "1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
SPREADSHEET_ID = "1qb6u5LyOGyp88EEx7PFSUKsZaNbuAsdbFJWoGTKcHEw"  # <── ISI SPREADSHEET ID DI SINI

# Nama sheet (tab) di dalam spreadsheet
SHEET_NAME = "Links"

# Nama PC ini (otomatis dari system)
PC_NAME = os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "Unknown-PC"))


# ═══════════════════════════════════════════════════════════════
#  INTERNAL
# ═══════════════════════════════════════════════════════════════

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_sheet = None
_sheet_lock = threading.RLock()  # reentrant lock — thread-safe, gak deadlock


def _get_sheet():
    """Get or create the worksheet connection (singleton, thread-safe)."""
    global _client, _sheet

    if _sheet is not None:
        return _sheet

    with _sheet_lock:
        # Double check setelah acquire lock
        if _sheet is not None:
            return _sheet

        if not GSPREAD_AVAILABLE:
            raise RuntimeError(
                "Library gspread belum terinstall!\n"
                "Jalankan: pip install gspread google-auth"
            )

        if not SPREADSHEET_ID:
            raise RuntimeError(
                "SPREADSHEET_ID belum diisi di cloud_storage.py!\n"
                "Buka Google Sheets → copy ID dari URL"
            )

        if not os.path.isfile(CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"credentials.json tidak ditemukan di:\n"
                f"  {CREDENTIALS_FILE}\n\n"
                f"Download dari Google Cloud Console → Service Account → Keys\n"
                f"Lalu taruh di folder python/"
            )

        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)

        # Set timeout 30 detik supaya tidak hang selamanya
        _client.http_client.session.timeout = 30

        spreadsheet = _client.open_by_key(SPREADSHEET_ID)

        # Coba buka sheet, kalau belum ada bikin baru + header
        try:
            _sheet = spreadsheet.worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            _sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=10000, cols=6)
            _sheet.update(values=[["No", "Timestamp", "PC", "Email", "Link", "Status"]], range_name="A1:F1")
            try:
                _sheet.format("A1:F1", {"textFormat": {"bold": True}})
            except Exception:
                pass  # formatting gagal gpp

        return _sheet


# ═══════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════

def save_link_cloud(link: str, email: str = "", status: str = "SUCCESS") -> bool:
    """
    Simpan 1 link ke Google Sheets.
    Thread-safe — bisa dipanggil dari banyak thread.
    Return True kalau berhasil, False kalau gagal.
    """
    try:
        with _sheet_lock:
            sheet = _get_sheet()
            all_values = sheet.col_values(1)  # kolom A
            next_row = len(all_values) + 1
            row_num = next_row - 1  # nomor urut (minus header)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sheet.update(
                values=[[row_num, timestamp, PC_NAME, email, link, status]],
                range_name=f"A{next_row}:F{next_row}"
            )

        print(f"☁️  Link disimpan ke Google Sheets (row {next_row})")
        return True

    except Exception as e:
        print(f"⚠️  Gagal simpan ke cloud: {e}")
        return False


def save_error_cloud(email: str, error_msg: str) -> bool:
    """Simpan error ke Google Sheets dengan status FAILED."""
    try:
        with _sheet_lock:
            sheet = _get_sheet()
            all_values = sheet.col_values(1)
            next_row = len(all_values) + 1
            row_num = next_row - 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sheet.update(
                values=[[row_num, timestamp, PC_NAME, email, error_msg[:300], "FAILED"]],
                range_name=f"A{next_row}:F{next_row}"
            )
        return True

    except Exception as e:
        print(f"⚠️  Gagal simpan error ke cloud: {e}")
        return False


def get_link_count() -> int:
    """Hitung total link SUCCESS di spreadsheet."""
    try:
        sheet = _get_sheet()
        statuses = sheet.col_values(6)  # kolom F = Status
        return sum(1 for v in statuses if v == "SUCCESS")
    except Exception:
        return -1


def is_cloud_ready() -> bool:
    """Cek apakah cloud storage siap dipakai."""
    if not GSPREAD_AVAILABLE:
        return False
    if not SPREADSHEET_ID:
        return False
    if not os.path.isfile(CREDENTIALS_FILE):
        return False
    return True


# ═══════════════════════════════════════════════════════════════
#  QUICK TEST — jalankan: python cloud_storage.py
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 50)
    print("  🧪 Test Cloud Storage → Google Sheets")
    print("=" * 50)
    print(f"  PC Name        : {PC_NAME}")
    print(f"  Credentials    : {CREDENTIALS_FILE}")
    print(f"  Spreadsheet ID : {SPREADSHEET_ID or '(BELUM DIISI!)'}")
    print(f"  gspread ready  : {GSPREAD_AVAILABLE}")
    print()

    if not GSPREAD_AVAILABLE:
        print("❌ gspread belum terinstall!")
        print("   Jalankan: pip install gspread google-auth")
        sys.exit(1)

    if not SPREADSHEET_ID:
        print("❌ SPREADSHEET_ID belum diisi!")
        print("   Edit cloud_storage.py → isi SPREADSHEET_ID")
        sys.exit(1)

    if not os.path.isfile(CREDENTIALS_FILE):
        print(f"❌ credentials.json tidak ditemukan di:")
        print(f"   {CREDENTIALS_FILE}")
        sys.exit(1)

    print("🔗 Mencoba koneksi ke Google Sheets...")
    print("   (kalau stuck >30 detik, cek firewall/antivirus)")
    print()

    # Test step by step supaya tau stuck di mana
    try:
        print("   [1/4] Loading credentials...")
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        print(f"   ✅ Service account: {creds.service_account_email}")

        print("   [2/4] Authorizing gspread...")
        client = gspread.authorize(creds)
        client.http_client.session.timeout = 30
        print("   ✅ Authorized")

        print(f"   [3/4] Opening spreadsheet {SPREADSHEET_ID[:20]}...")
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print(f"   ✅ Spreadsheet: {spreadsheet.title}")

        print("   [4/4] Writing test row...")
        ok = save_link_cloud(
            link="https://one.google.com/offer/TEST12345",
            email="test@example.com",
            status="TEST"
        )
        if ok:
            print()
            print("✅ BERHASIL! Cek Google Sheets mu — harusnya ada row baru.")
            count = get_link_count()
            if count >= 0:
                print(f"📊 Total links SUCCESS: {count}")
        else:
            print("❌ Gagal menulis ke spreadsheet.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
