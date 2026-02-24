# 🖥️ Setup VPS & Tutorial Jalankan Bot

## 📋 Minimum Spek VPS

| Threads | vCPU | RAM    | Disk  | Catatan                     |
|---------|------|--------|-------|-----------------------------|
| 1       | 2    | 2 GB   | 20 GB | Minimum, wajib tambah SWAP  |
| 1-2     | 2    | 4 GB   | 30 GB | Recommended untuk mulai     |
| 4       | 4    | 8 GB   | 40 GB | Smooth                      |
| 6       | 6-8  | 16 GB  | 40 GB | Optimal                     |
| 8       | 8    | 32 GB  | 50 GB | Full speed                  |

> 1 browser ≈ 500-800 MB RAM. Formula: `max_threads = (Total RAM - 2 GB) / 1 GB`

**OS:** Ubuntu 22.04 atau 24.04 LTS
**Provider:** Contabo, Hetzner, DigitalOcean, Vultr, Tencent Cloud

---

## 🚀 Setup VPS (Step by Step)

### 1. Login ke VPS
```bash
ssh root@IP_VPS_KAMU
```

### 2. Update system
```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Install dependencies
```bash
sudo apt install -y python3 python3-pip python3-venv python3-full git wget curl unzip xvfb tmux
```

### 4. Install Brave Browser (recommended)
```bash
sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg \
  https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" \
  | sudo tee /etc/apt/sources.list.d/brave-browser-release.list

sudo apt update && sudo apt install -y brave-browser
```

**Atau install Chrome (alternatif):**
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt -f install -y
```

### 5. Tambah SWAP (WAJIB untuk VPS ≤ 4 GB RAM)
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Verifikasi swap aktif:
```bash
free -h
```

---

## 📦 Upload File Bot ke VPS

### Dari Windows (PowerShell/CMD):
```bash
scp -r "D:\bot create\python\*" root@IP_VPS_KAMU:~/bot/python/
```

> Kalau folder belum ada di VPS, buat dulu:
> ```bash
> ssh root@IP_VPS_KAMU "mkdir -p ~/bot/python"
> ```

### File yang perlu ada di VPS:
```
~/bot/python/
├── autogemini.py          ← bot utama
├── vcc_generator.py       ← generator VCC
├── name_generator.py      ← generator nama
├── cloud_storage.py       ← (opsional) Google Sheets
├── credentials.json       ← (opsional) Google Sheets
├── bin-config.json        ← konfigurasi BIN
├── vcc-list.txt           ← (opsional) daftar VCC
├── proxy-list.txt         ← daftar proxy
└── requirements.txt       ← dependencies Python
```

---

## 🐍 Install Python Dependencies

```bash
cd ~/bot/python

# Buat virtual environment (wajib di Ubuntu 24.04+)
python3 -m venv venv

# Aktifkan virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## ▶️ Jalankan Bot

### Cara 1: Langsung (SSH tetap terbuka)
```bash
cd ~/bot/python
source venv/bin/activate
xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" python3 autogemini.py
```

### Cara 2: Dengan tmux (SSH bisa ditutup, bot tetap jalan) ← RECOMMENDED
```bash
# Buat session tmux baru
tmux new -s bot

# Di dalam tmux, jalankan bot
cd ~/bot/python
source venv/bin/activate
xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" python3 autogemini.py
```

**Perintah tmux:**
| Aksi                        | Cara                          |
|-----------------------------|-------------------------------|
| Detach (bot tetap jalan)    | `Ctrl+B` lalu `D`            |
| Re-attach (balik ke bot)    | `tmux attach -t bot`         |
| Kill session (stop semua)   | Ketik `exit` atau `Ctrl+D`   |
| List sessions               | `tmux ls`                    |

---

## 🔄 Update File Bot

Kalau ada perubahan code, upload ulang dari Windows:
```bash
scp "D:\bot create\python\autogemini.py" root@IP_VPS_KAMU:~/bot/python/
```

Lalu restart bot di VPS:
```bash
tmux attach -t bot
# Ctrl+C untuk stop bot
# Jalankan ulang
xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" python3 autogemini.py
```

---

## 📊 Monitoring

### Cek RAM & CPU real-time:
```bash
htop
```
> Install dulu kalau belum: `sudo apt install htop`

### Cek disk usage:
```bash
df -h
```

### Lihat log error:
```bash
cat ~/bot/python/logs/errors.txt
```

### Lihat hasil link:
```bash
cat ~/bot/python/links.txt
```

### Cek apakah browser masih jalan:
```bash
ps aux | grep -E "brave|chrome"
```

### Kill semua browser manual (darurat):
```bash
pkill -9 -f brave
pkill -9 -f chrome
pkill -9 -f chromedriver
```

---

## ⚙️ Setting Rekomendasi per VPS

### VPS 2 GB RAM
```
Thread     : 1
Browser    : Visible (via xvfb)
SWAP       : 2 GB (wajib)
Cooldown   : setiap 10 akun
Auto-retry : 2x
```

### VPS 4 GB RAM
```
Thread     : 2
Browser    : Visible (via xvfb)
SWAP       : 2 GB (disarankan)
Cooldown   : setiap 10 akun
Auto-retry : 2x
```

### VPS 8 GB RAM
```
Thread     : 4
Browser    : Visible (via xvfb)
Cooldown   : setiap 10 akun
Auto-retry : 2x
```

### VPS 16-32 GB RAM
```
Thread     : 6-8
Browser    : Visible (via xvfb)
Cooldown   : setiap 10 akun
Auto-retry : 2x
```

---

## ❓ Troubleshooting

### "Brave atau Chrome tidak ditemukan"
```bash
# Cek apakah browser terinstall
which brave-browser
which google-chrome
```

### "externally-managed-environment"
Pakai virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### CPU 100% / RAM penuh
```bash
# Kill semua browser
pkill -9 -f brave && pkill -9 -f chromedriver

# Cek swap
free -h

# Kurangi thread atau tambah cooldown
```

### Bot mati setelah SSH ditutup
Pastikan pakai **tmux**. Detach dengan `Ctrl+B` lalu `D` sebelum tutup SSH.

### "proxy-list.txt not found"
Pastikan file ada di folder yang sama dengan `autogemini.py`:
```bash
ls ~/bot/python/proxy-list.txt
```

### Permission denied
```bash
chmod +x ~/bot/python/autogemini.py
```

---

## 🔑 Format File

### proxy-list.txt
```
# Satu proxy per baris — format: host:port:username:password
growtechcentral.com:10000:user123:pass456
growtechcentral.com:10001:user123:pass456
growtechcentral.com:10002:user123:pass456
```

### bin-config.json
```json
[
    { "bin": "62581426", "expMonth": "01", "expYear": "34" }
]
```

### vcc-list.txt
```
6258142684510676|10|34|123
5388410551828785|12|33|456
```
