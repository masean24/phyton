# 📖 Tutorial Auto Gemini AI Pro Bot (Python)

Panduan lengkap dari awal sampai running, termasuk setup Google Sheets cloud storage.

---

## 📋 Daftar Isi

1. [Kebutuhan System](#-1-kebutuhan-system)
2. [Install Python](#-2-install-python)
3. [Download Project](#-3-download-project)
4. [Install Dependencies](#-4-install-dependencies)
5. [Setup Browser (Brave/Chrome)](#-5-setup-browser)
6. [Setup BIN Config](#-6-setup-bin-config)
7. [Setup VCC List (opsional)](#-7-setup-vcc-list-opsional)
8. [Menjalankan Bot](#-8-menjalankan-bot)
9. [Setup Google Sheets Cloud Storage](#-9-setup-google-sheets-cloud-storage)
10. [Running di Banyak PC](#-10-running-di-banyak-pc)
11. [Troubleshooting](#-11-troubleshooting)

---

## 🖥 1. Kebutuhan System

- **Windows 10/11** (64-bit)
- **Python 3.10+** (direkomendasikan 3.12 atau 3.13)
- **Brave Browser** atau **Google Chrome** (terinstall)
- **Koneksi internet**

---

## 🐍 2. Install Python

1. Buka https://www.python.org/downloads/
2. Download versi terbaru (3.12+)
3. Saat install, **CENTANG** ✅ `Add Python to PATH`
4. Klik Install Now
5. Verifikasi di terminal:

```powershell
python --version
# Python 3.13.x
```

> Atau install dari **Microsoft Store** → cari "Python 3.13"

---

## 📂 3. Download Project

Copy folder `python\` ke PC:

```
python\
├── autogemini.py      ← 🤖 BOT UTAMA
├── cloud_storage.py   ← ☁️ Google Sheets module
├── vcc_generator.py   ← generator VCC
├── name_generator.py  ← generator nama
├── requirements.txt
├── bin-config.json    ← 💳 konfigurasi BIN
├── vcc-list.txt       ← 💳 daftar VCC (opsional)
├── credentials.json   ← 🔑 Google API key (kamu buat sendiri)
├── links.txt          ← output link (auto dibuat)
├── TUTORIAL.md        ← 📖 file ini
└── logs\
    └── errors.txt
```

> **Gak perlu copy file TypeScript!** Folder `python/` bisa jalan sendiri (standalone).

---

## 📦 4. Install Dependencies

Buka terminal di folder `python\`:

```powershell
cd "D:\bot create\gemini 3 month\python"
pip install -r requirements.txt
```

Ini akan install:
- `undetected-chromedriver` — browser automation anti-detect
- `selenium` — web driver
- `requests` — HTTP client
- `gspread` — Google Sheets API *(opsional, untuk cloud storage)*
- `google-auth` — Google authentication *(opsional)*

---

## 🌐 5. Setup Browser

Bot butuh **Brave** atau **Chrome** yang sudah terinstall.

### Brave (Recommended)
Install dari: https://brave.com/download/

Default path:
```
C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
```

### Chrome
Default path:
```
C:\Program Files\Google\Chrome\Application\chrome.exe
```

> Bot akan auto-detect browser yang terinstall. Brave dicek duluan.

---

## 💳 6. Setup BIN Config

Edit file `bin-config.json` di folder `python\`:

```json
[
  {
    "bin": "453201",
    "expMonth": "12",
    "expYear": "2028"
  }
]
```

- `bin` — 6 digit pertama kartu (BIN)
- `expMonth` — bulan expired (2 digit)
- `expYear` — tahun expired (4 digit)

Bisa masukkan beberapa BIN sekaligus:

```json
[
  { "bin": "453201", "expMonth": "12", "expYear": "2028" },
  { "bin": "421345", "expMonth": "06", "expYear": "2027" }
]
```

---

## 📄 7. Setup VCC List (opsional)

Kalau sudah punya daftar VCC lengkap, taruh di folder `python\` sebagai `vcc-list.txt`:

```
4532012345678901|12|2028|123
4213451234567890|06|2027|456
```

Format per baris: `NOMOR_KARTU|BULAN|TAHUN|CVC`

---

## ▶️ 8. Menjalankan Bot

```powershell
cd "D:\bot create\gemini 3 month\python"
python autogemini.py
```

Bot akan tanya:

```
Mode email: (1) Random generate  (2) API Hubify  [1/2]:
```
→ Ketik `1` untuk random email, `2` untuk API

```
Mode VCC: (1) Generate dari BIN  (2) Dari file vcc-list.txt  [1/2]:
```
→ Ketik `1` kalau pakai BIN config, `2` kalau pakai vcc-list.txt

```
Berapa akun? [default 1]:
```
→ Jumlah akun yang mau dibuat

```
Berapa thread? [default 1]:
```
→ Jumlah browser yang jalan bersamaan (2-3 recommended)

```
Headless mode? (y/n) [n]:
```
→ `n` = browser terlihat, `y` = background (tanpa tampilan)

### Output

Link yang berhasil akan disimpan ke:
- **`links.txt`** — file lokal (1 link per baris)
- **Google Sheets** — kalau cloud storage aktif *(lihat Setup di bawah)*

---

## ☁️ 9. Setup Google Sheets Cloud Storage

Fitur ini **opsional** tapi sangat berguna kalau mau running di banyak PC — semua link dikumpulkan ke 1 spreadsheet.

### Step 1: Buat Google Cloud Project

1. Buka https://console.cloud.google.com/
2. Klik **Select a project** → **New Project**
3. Nama project: `gemini-bot` (bebas)
4. Klik **Create**

### Step 2: Enable Google Sheets API

1. Di sidebar kiri, klik **APIs & Services** → **Library**
2. Cari **"Google Sheets API"**
3. Klik → **Enable**
4. Cari juga **"Google Drive API"** → **Enable**

### Step 3: Buat Service Account

1. Di sidebar kiri: **APIs & Services** → **Credentials**
2. Klik **+ CREATE CREDENTIALS** → **Service account**
3. Isi nama: `gemini-bot-sheets` (bebas)
4. Klik **Create and Continue**
5. Di "Grant this service account access":
   - Role: **Editor**
   - Klik **Continue** → **Done**

### Step 4: Download credentials.json

1. Di halaman Credentials, klik service account yang baru dibuat
2. Tab **Keys** → **Add Key** → **Create new key**
3. Pilih **JSON** → **Create**
4. File JSON otomatis terdownload
5. **Rename** jadi `credentials.json`
6. **Pindahkan** ke folder `python\`:

```
D:\bot create\gemini 3 month\python\credentials.json
```

### Step 5: Buat Google Spreadsheet

1. Buka https://docs.google.com/spreadsheets/
2. Klik **+ Blank** (buat spreadsheet baru)
3. Kasih nama: `Gemini Bot Links` (bebas)
4. **Copy Spreadsheet ID** dari URL:

```
https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ/edit
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       INI SPREADSHEET ID-NYA
```

### Step 6: Share Spreadsheet ke Service Account

1. Buka `credentials.json` yang tadi di-download
2. Cari field `"client_email"`, contoh:

```json
"client_email": "gemini-bot-sheets@gemini-bot-123456.iam.gserviceaccount.com"
```

3. Di Google Sheets, klik tombol **Share** (kanan atas)
4. Paste email service account tersebut
5. Set permission: **Editor**
6. Klik **Send** (uncheck "Notify people" kalau mau)

### Step 7: Isi SPREADSHEET_ID di cloud_storage.py

Buka file `python/cloud_storage.py`, cari baris ini:

```python
SPREADSHEET_ID = ""  # <── ISI SPREADSHEET ID DI SINI
```

Isi dengan ID yang tadi di-copy:

```python
SPREADSHEET_ID = "1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
```

### Step 8: Test!

```powershell
cd "D:\bot create\gemini 3 month\python"
python cloud_storage.py
```

Kalau berhasil:
```
✅ BERHASIL! Cek Google Sheets mu — harusnya ada row baru.
📊 Total links SUCCESS: 0
```

Buka Google Sheets — harusnya ada row test.

### Step 9: Jalankan Bot

```powershell
python autogemini.py
```

Sekarang di awal akan tertulis:
```
☁️  Cloud Storage: ✅ AKTIF — link akan disimpan ke Google Sheets
```

Setiap link yang berhasil otomatis masuk ke spreadsheet:

| No | Timestamp           | PC        | Email                      | Link                          | Status  |
|----|---------------------|-----------|----------------------------|-------------------------------|---------|
| 1  | 2026-02-23 14:30:01 | PC-KANTOR | bright_fox2341@gmail.com   | https://one.google.com/offer/... | SUCCESS |
| 2  | 2026-02-23 14:35:00 | PC-RUMAH  | swift_bear1823@yahoo.com   | https://one.google.com/offer/... | SUCCESS |
| 3  | 2026-02-23 14:40:12 | PC-KANTOR | calm_wolf5512@outlook.com  | Payment failed              | FAILED  |

---

## 🖥 10. Running di Banyak PC

### Setup di Setiap PC:

1. **Copy** folder `python\` ke PC baru (cukup folder ini aja!)
2. **Install Python** (lihat Step 2)
3. **Install dependencies:**
   ```powershell
   cd "path\ke\python"
   pip install -r requirements.txt
   ```
4. **File yang harus SAMA di semua PC:**
   - `credentials.json` ← copy yang sama
   - `cloud_storage.py` ← SPREADSHEET_ID harus sama
   - `bin-config.json` ← BIN config (atau beda juga boleh)

5. **Jalankan bot:**
   ```powershell
   python autogemini.py
   ```

Semua PC akan **otomatis append** ke 1 spreadsheet yang sama! 🎉

### Tips Multi-PC:

- Setiap PC otomatis namanya tercatat di kolom **PC** (nama komputer)
- Kalau mau ganti nama PC di spreadsheet, edit `PC_NAME` di `cloud_storage.py`
- Link lokal tetap disimpan ke `links.txt` per PC sebagai backup
- Kalau internet mati, link tetap tersimpan lokal — cloud gagal doang

---

## 🔧 11. Troubleshooting

### ❌ `ModuleNotFoundError: No module named 'undetected_chromedriver'`
```powershell
pip install undetected-chromedriver
```

### ❌ `ModuleNotFoundError: No module named 'gspread'`
```powershell
pip install gspread google-auth
```
> Cloud storage bersifat opsional. Bot tetap jalan tanpa gspread.

### ❌ `FileNotFoundError: credentials.json tidak ditemukan`
- Pastikan `credentials.json` ada di folder `python\`
- Download ulang dari Google Cloud Console → Service Account → Keys

### ❌ `SPREADSHEET_ID belum diisi`
- Buka `cloud_storage.py` → isi `SPREADSHEET_ID = "..."`

### ❌ `403 Forbidden / permission denied` di Google Sheets
- Pastikan spreadsheet sudah di-**Share** ke email service account
- Pastikan permission = **Editor** (bukan Viewer)

### ❌ `[WinError 183] Cannot create a file when that file already exists`
- Race condition saat 2 thread launch browser bersamaan
- **Sudah difix** dengan Lock — pastikan pakai versi terbaru `autogemini.py`

### ❌ Browser tidak ditemukan
- Install **Brave** dari https://brave.com/download/
- Atau **Chrome** dari https://www.google.com/chrome/

### ❌ Bot stuck / timeout
- Cek koneksi internet
- Coba dengan `headless = n` supaya bisa lihat browser  
- Cek `logs/errors.txt` untuk detail error
- Cek folder `python/logs/` untuk screenshot error

### ❌ Country dropdown tidak terpilih
- Sudah difix di versi terbaru — bot sekarang support React-Select dropdown di Coursera

### ❌ Link tidak muncul di spreadsheet padahal bot jalan
- Jalankan test: `python cloud_storage.py`
- Pastikan `credentials.json` ada dan SPREADSHEET_ID benar
- Cek apakah service account sudah di-share ke spreadsheet

---

## 📁 Struktur File Lengkap

```
python\
├── autogemini.py        ← 🤖 BOT UTAMA PYTHON
├── cloud_storage.py     ← ☁️ Module Google Sheets
├── credentials.json     ← 🔑 Google API key (JANGAN SHARE!)
├── bin-config.json      ← 💳 Konfigurasi BIN
├── vcc-list.txt         ← 💳 Daftar VCC (opsional)
├── vcc_generator.py     ← Generator VCC
├── name_generator.py    ← Generator nama Indonesia
├── requirements.txt     ← Daftar dependencies
├── links.txt            ← Output link (auto dibuat)
├── TUTORIAL.md          ← 📖 File ini
└── logs\
    └── errors.txt
```

> Folder `python/` sepenuhnya **standalone** — gak perlu file TypeScript sama sekali.

---

## ⚠️ Penting!

- **JANGAN SHARE** `credentials.json` ke orang lain — itu seperti password Google API kamu
- File `links.txt` lokal tetap jadi **backup** walaupun cloud aktif
- Kalau mau **matikan cloud**, kosongkan `SPREADSHEET_ID` di `cloud_storage.py` atau hapus `credentials.json`
- Bot tetap berjalan normal **tanpa cloud** — fitur ini 100% opsional

---

*Last updated: Februari 2026*
