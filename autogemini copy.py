"""
Auto Gemini AI Pro — Bot Generator (Python / undetected-chromedriver)
Full port dari autogemini.ts

Flow (18 step):
  1. grow.google → "Mulai sekarang"
  2. Coursera → "Enroll for free"
  3-6. Signup: email → nama → password → "Join for Free"
  7. "Start Free Trial"
  8. Checkout: pilih Indonesia
  9. Isi VCC (Braintree / Stripe / Direct)
  10. Submit payment
  11. "My commitment" checkbox → "Start the course"
  12. Success popup → Continue
  13. Module 2
  14. "Redeem your Google AI Pro trial"
  15-16. Agree checkbox → "Launch App"
  17-18. Extract offer link dari saritasa.cloud
"""

import os
import re
import sys
import json
import time
import random
import string
import shutil
import tempfile
import traceback
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List
import threading

import zipfile
import psutil
from dataclasses import dataclass

import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementNotInteractableException,
    StaleElementReferenceException, WebDriverException, ElementClickInterceptedException,
)

from vcc_generator import (
    VCCConfig, GeneratedVCC, generate_vcc, parse_vcc_line, validate_bin,
)
from name_generator import generate_random_name

# ── Cloud Storage (opsional — simpan link ke Google Sheets) ──
try:
    from cloud_storage import save_link_cloud, save_error_cloud, is_cloud_ready
    CLOUD_ENABLED = is_cloud_ready()
except ImportError:
    CLOUD_ENABLED = False

    def save_link_cloud(*a, **kw): return False
    def save_error_cloud(*a, **kw): return False

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

HUBIFY_API = "https://mail.hubify.store/api/ext"
HUBIFY_API_KEY = "Ct]yJP$&Q)[b!V5([yT%Q*@3{@U.z@$p1yX+cAZJ@KU4A03@F("
# Output: cek folder python/ dulu, fallback ke parent
_SELF_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.join(_SELF_DIR, "..")
OUTPUT_FILE = os.path.join(_SELF_DIR, "links.txt")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
ERROR_LOG = os.path.join(LOGS_DIR, "errors.txt")
PROFILES_DIR = os.path.join(tempfile.gettempdir(), "gemini-bot-profiles-py")

# Ensure dirs exist
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)

# Lock untuk uc.Chrome() — mencegah race condition saat patching chromedriver
_chrome_launch_lock = threading.Lock()
PROXY_EXT_DIR = os.path.join(tempfile.gettempdir(), "gemini-proxy-extensions")
os.makedirs(PROXY_EXT_DIR, exist_ok=True)

# ── RAM threshold (MB) — jangan launch browser baru kalau RAM tersisa < ini
MIN_FREE_RAM_MB = 1500  # 1.5 GB minimum


def check_ram_available() -> bool:
    """Cek apakah RAM cukup untuk launch browser baru."""
    try:
        mem = psutil.virtual_memory()
        free_mb = mem.available / (1024 * 1024)
        return free_mb >= MIN_FREE_RAM_MB
    except Exception:
        return True  # kalau psutil gagal, lanjut aja


def wait_for_ram(tag: str, timeout: int = 120) -> bool:
    """Tunggu sampai RAM cukup, max timeout detik. Return True jika RAM OK."""
    if check_ram_available():
        return True
    print(f"{tag} ⏳ RAM rendah, menunggu RAM tersedia (min {MIN_FREE_RAM_MB} MB)...")
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(5)
        if check_ram_available():
            try:
                mem = psutil.virtual_memory()
                free_mb = mem.available / (1024 * 1024)
                print(f"{tag} ✅ RAM tersedia: {free_mb:.0f} MB")
            except Exception:
                pass
            return True
    print(f"{tag} ⚠️ RAM masih rendah setelah {timeout}s, lanjut paksa...")
    return False


# ═══════════════════════════════════════════════════════════════
#  PROXY — authenticated proxy via Chrome extension (MV2)
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProxyConfig:
    host: str
    port: str
    username: str
    password: str

    @property
    def display(self) -> str:
        return f"{self.host}:{self.port} (user: {self.username[:8]}...)"


def parse_proxy(line: str) -> Optional[ProxyConfig]:
    """
    Parse proxy string format: host:port:username:password
    Contoh: growtechcentral.com:10000:ca985b86519d8d3b5068__cr.id:0324ca8617654dad
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(":")
    if len(parts) < 4:
        return None
    host = parts[0]
    port = parts[1]
    # Username & password bisa mengandung ':', jadi gabung sisa parts
    # Format: host:port:username:password
    # Tapi username bisa ada ':' (misal user__cr.id) — kita split jadi 4 max
    # Strategi: host=parts[0], port=parts[1], user=parts[2], pass=sisanya
    username = parts[2]
    password = ":".join(parts[3:])  # password bisa punya ':'
    if not host or not port or not username or not password:
        return None
    return ProxyConfig(host=host, port=port, username=username, password=password)


def load_proxy_list(filepath: str) -> List[ProxyConfig]:
    """Load daftar proxy dari file, satu per baris."""
    proxies = []
    try:
        lines = Path(filepath).read_text(encoding="utf-8").splitlines()
        for line in lines:
            p = parse_proxy(line)
            if p:
                proxies.append(p)
    except Exception as e:
        print(f"⚠️ Gagal load proxy list: {e}")
    return proxies


def create_proxy_auth_extension(proxy: ProxyConfig, thread_id: int = 0) -> str:
    """
    Buat Chrome extension (MV2) untuk proxy authenticated.
    Return path ke folder extension yang sudah di-extract.
    Brave & Chromium support MV2 extensions via --load-extension.
    """
    ext_dir = os.path.join(PROXY_EXT_DIR, f"proxy-ext-t{thread_id}-{int(time.time())}")
    os.makedirs(ext_dir, exist_ok=True)

    manifest = json.dumps({
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy Auth",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version": "76.0.0"
    }, indent=2)

    background_js = f"""var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{
            scheme: "http",
            host: "{proxy.host}",
            port: parseInt("{proxy.port}")
        }},
        bypassList: [
            "localhost",
            "*.stripe.com",
            "*.braintreegateway.com",
            "*.braintree-api.com",
            "*.paypal.com",
            "*.gstatic.com",
            "*.googleapis.com",
            "*.google.com",
            "*.googleusercontent.com",
            "*.accounts.google.com"
        ]
    }}
}};

chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

function callbackFn(details) {{
    return {{
        authCredentials: {{
            username: "{proxy.username}",
            password: "{proxy.password}"
        }}
    }};
}}

chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {{urls: ["<all_urls>"]}},
    ['blocking']
);
"""

    with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(manifest)
    with open(os.path.join(ext_dir, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)

    return ext_dir


def cleanup_proxy_extensions() -> None:
    """Hapus semua temp proxy extension folders."""
    try:
        if os.path.exists(PROXY_EXT_DIR):
            shutil.rmtree(PROXY_EXT_DIR, ignore_errors=True)
    except Exception:
        pass
    os.makedirs(PROXY_EXT_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def random_delay(min_ms: int, max_ms: int) -> None:
    """Sleep untuk durasi acak (miliseconds)."""
    time.sleep(random.randint(min_ms, max_ms) / 1000.0)


def random_from(arr: list):
    return random.choice(arr)


def generate_password(length: int = 14) -> str:
    chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%"
    return "".join(random.choice(chars) for _ in range(length))


def log_error(tag: str, email: str, message: str) -> None:
    ts = datetime.now().isoformat()
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {tag} {email} - {message}\n")


def save_screenshot(driver, tag: str, prefix: str = "error") -> None:
    try:
        fname = f"{prefix}-{tag}-{int(time.time())}.png"
        driver.save_screenshot(os.path.join(LOGS_DIR, fname))
    except Exception:
        pass


def _elements_displayed(driver, by: str, value: str):
    try:
        els = driver.find_elements(getattr(By, by), value)
        return [e for e in els if e.is_displayed()]
    except Exception:
        return []


def dismiss_common_modals(driver, tag: str) -> None:
    """Best-effort: close/continue any Coursera/CDS modal that can intercept clicks."""
    try:
        # Try ESC first (many dialogs close on ESC)
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.2)
    except Exception:
        pass

    # Common buttons seen in Coursera flows
    button_texts = [
        "Continue",
        "Close",
        "Got it",
        "OK",
        "No thanks",
        "Not now",
        "Dismiss",
    ]
    for txt in button_texts:
        try:
            btns = driver.find_elements(By.XPATH, f"//button[contains(normalize-space(.), '{txt}')] | //a[contains(normalize-space(.), '{txt}')]")
            for b in btns:
                if b.is_displayed():
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    except Exception:
                        pass
                    try:
                        b.click()
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", b)
                        except Exception:
                            pass
                    random_delay(300, 700)
                    # One click may close the modal; keep scanning
        except Exception:
            pass

    # Click backdrop if present
    try:
        backdrops = driver.find_elements(By.CSS_SELECTOR, ".cds-Modal-backdrop, .cds-Modal-container")
        for bd in backdrops:
            if bd.is_displayed():
                try:
                    driver.execute_script("arguments[0].click();", bd)
                    random_delay(200, 500)
                except Exception:
                    pass
    except Exception:
        pass

    # Wait briefly until modal container is gone (don’t block too long)
    try:
        WebDriverWait(driver, 3).until_not(
            EC.visibility_of_any_elements_located((By.CSS_SELECTOR, ".cds-Modal-container"))
        )
    except Exception:
        # still visible — caller may retry
        pass


def safe_click(driver, element, tag: str, desc: str = "") -> None:
    """Click with retries, handling overlays/modals that intercept clicks."""
    if desc:
        print(f"{tag} 🖱️ Click: {desc}")

    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            except Exception:
                pass
            random_delay(200, 600)
            element.click()
            return
        except ElementClickInterceptedException as e:
            last_err = e
            print(f"{tag} ⚠️ Click intercepted (attempt {attempt}) — dismissing modal...")
            dismiss_common_modals(driver, tag)
            random_delay(300, 900)
        except (StaleElementReferenceException, ElementNotInteractableException, WebDriverException) as e:
            last_err = e
            # Try JS click as fallback on last attempt
            if attempt >= 3:
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return
                except Exception as e2:
                    last_err = e2
            random_delay(300, 900)

    if last_err:
        raise last_err


# ═══════════════════════════════════════════════════════════════
#  VPN ROTATION
# ═══════════════════════════════════════════════════════════════

VPN_CLI = {
    "nordvpn":    {"disconnect": "nordvpn -d",            "connect": "nordvpn -c"},
    "expressvpn": {"disconnect": "expressvpn disconnect",  "connect": "expressvpn connect"},
    "windscribe": {"disconnect": "windscribe disconnect",  "connect": "windscribe connect best"},
}


def run_cmd(cmd: str) -> None:
    print(f"  🔧 [VPN] Jalankan: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.stdout.strip():
            print(f"     stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"     stderr: {result.stderr.strip()}")
    except Exception as e:
        print(f"     ⚠️  Error: {e}")


def rotate_vpn(vpn_type: str, disconnect_cmd: str = "", connect_cmd: str = "") -> None:
    if vpn_type == "none":
        return

    if vpn_type == "custom":
        cmds = {"disconnect": disconnect_cmd, "connect": connect_cmd}
    else:
        cmds = VPN_CLI.get(vpn_type, {"disconnect": "", "connect": ""})

    print("\n🔄 [VPN] Merotasi IP...")
    run_cmd(cmds["disconnect"])
    time.sleep(3)
    run_cmd(cmds["connect"])
    time.sleep(6)
    print("✅ [VPN] IP sudah dirotasi\n")


# ═══════════════════════════════════════════════════════════════
#  ANTI-DETECT — fingerprint randomization
# ═══════════════════════════════════════════════════════════════

SCREEN_SIZES = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720),  (1600, 900), (1280, 800), (1680, 1050),
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

LOCALES = ["en-US", "en-GB"]
TIMEZONES = ["Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura"]

STEALTH_JS = """
// Extra stealth di atas undetected-chromedriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

if (!window.chrome) window.chrome = {};
window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };
window.chrome.loadTimes = () => ({
  commitLoadTime: Date.now() / 1000,
  connectionInfo: 'h2',
  finishDocumentLoadTime: Date.now() / 1000,
  finishLoadTime: Date.now() / 1000,
  firstPaintAfterLoadTime: 0,
  firstPaintTime: Date.now() / 1000,
  navigationType: 'Other',
  npnNegotiatedProtocol: 'h2',
  requestTime: Date.now() / 1000,
  startLoadTime: Date.now() / 1000,
  wasAlternateProtocolAvailable: false,
  wasFetchedViaSpdy: true,
  wasNpnNegotiated: true,
});
window.chrome.csi = () => ({
  onloadT: Date.now(), pageT: Date.now(), startE: Date.now(), tran: 15,
});

// Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters);

// Override plugins
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const p = [
      { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1 },
      { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 2 },
    ];
    p.refresh = () => {};
    return p;
  },
});

// Override mimeTypes
Object.defineProperty(navigator, 'mimeTypes', {
  get: () => {
    const m = [
      { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
      { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' },
    ];
    m.refresh = () => {};
    return m;
  },
});

Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'id'] });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => ~~HWCONCURRENCY~~ });
Object.defineProperty(navigator, 'deviceMemory', { get: () => ~~DEVMEM~~ });

// WebGL vendor/renderer
const _getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
  if (p === 37445) return 'Intel Inc.';
  if (p === 37446) return 'Intel Iris OpenGL Engine';
  return _getParam.call(this, p);
};

// Canvas noise
const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
  if (type === 'image/png' && this.width > 16) {
    const ctx = this.getContext('2d');
    if (ctx) {
      const d = ctx.getImageData(0, 0, this.width, this.height);
      for (let i = 0; i < d.data.length; i += 4) { d.data[i] ^= 1; }
      ctx.putImageData(d, 0, 0);
    }
  }
  return _toDataURL.apply(this, arguments);
};

// Notification
if (typeof Notification !== 'undefined') {
  Object.defineProperty(Notification, 'permission', { get: () => 'default' });
}

// Connection info
Object.defineProperty(navigator, 'connection', {
  get: () => ({ effectiveType: '4g', rtt: ~~RTT~~, downlink: ~~DOWNLINK~~, saveData: false }),
});
"""


def build_stealth_js() -> str:
    """Build stealth JS with randomized values."""
    js = STEALTH_JS
    js = js.replace("~~HWCONCURRENCY~~", str(random.randint(4, 16)))
    js = js.replace("~~DEVMEM~~", str(random.choice([4, 8, 16])))
    js = js.replace("~~RTT~~", str(random.randint(50, 200)))
    js = js.replace("~~DOWNLINK~~", f"{1.5 + random.random() * 8.5:.1f}")
    return js


# ═══════════════════════════════════════════════════════════════
#  BROWSER — find Brave / Chrome
# ═══════════════════════════════════════════════════════════════

def find_browser_path() -> tuple[str, str]:
    """Return (path, name) — Brave prioritized over Chrome."""
    home = os.path.expanduser("~")
    browsers = [
        ("Brave", [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.join(home, "AppData", "Local", "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]),
        ("Chrome", [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(home, "AppData", "Local", "Google", "Chrome", "Application", "chrome.exe"),
        ]),
    ]
    for name, paths in browsers:
        for p in paths:
            if os.path.isfile(p):
                print(f"🌐 Browser ditemukan: {name} → {p}")
                return p, name
    raise FileNotFoundError("Brave atau Chrome tidak ditemukan! Install salah satu dulu.")


def create_profile_dir(thread_id: int) -> str:
    p = os.path.join(PROFILES_DIR, f"profile-{thread_id}-{int(time.time()*1000)}")
    os.makedirs(p, exist_ok=True)
    return p


def delete_profile_dir(p: str) -> None:
    try:
        shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass


def cleanup_all_profiles() -> None:
    try:
        if os.path.exists(PROFILES_DIR):
            shutil.rmtree(PROFILES_DIR, ignore_errors=True)
    except Exception:
        pass
    os.makedirs(PROFILES_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
#  EMAIL
# ═══════════════════════════════════════════════════════════════

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "live.com", "protonmail.com", "mail.com",
    "ymail.com", "googlemail.com",
]

_ADJ = ["bright","swift","calm","neat","bold","keen","wise","cool","deep","fair","glad","warm","soft","wild","pure"]
_NOUN = ["fox","bear","wolf","hawk","lion","star","moon","sun","sky","sea","oak","ivy","ash","bay","elm"]


def generate_random_email() -> str:
    adj = random.choice(_ADJ)
    noun = random.choice(_NOUN)
    sep = random.choice([".", "_", ""])
    num = random.randint(100, 9099)
    domain = random.choice(EMAIL_DOMAINS)
    return f"{adj}{sep}{noun}{num}@{domain}"


def create_temp_email(use_api: bool) -> str:
    if not use_api:
        return generate_random_email()
    resp = requests.post(
        f"{HUBIFY_API}/inbox/create",
        json={},
        headers={"X-API-Key": HUBIFY_API_KEY, "Content-Type": "application/json"},
        timeout=15,
    )
    data = resp.json()
    if data.get("success"):
        return data["data"]["email"]
    raise RuntimeError("Hubify API returned success: false")


def delete_temp_email(email: str, use_api: bool) -> None:
    if not use_api:
        return
    try:
        requests.delete(
            f"{HUBIFY_API}/inbox/{email}",
            headers={"X-API-Key": HUBIFY_API_KEY},
            timeout=10,
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  HUMAN-LIKE TYPING
# ═══════════════════════════════════════════════════════════════

def human_type(element, text: str) -> None:
    """Ketik karakter satu-satu dengan delay acak."""
    element.click()
    random_delay(200, 500)
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(0.05, 0.18))


def human_type_keys(driver, element, text: str) -> None:
    """Ketik via ActionChains — fallback kalau element.send_keys gagal."""
    actions = ActionChains(driver)
    actions.click(element)
    actions.pause(random.uniform(0.2, 0.5))
    for ch in text:
        actions.send_keys(ch)
        actions.pause(random.uniform(0.05, 0.18))
    actions.perform()


# ═══════════════════════════════════════════════════════════════
#  MAIN BOT FLOW
# ═══════════════════════════════════════════════════════════════

def run_bot(
    thread_id: int,
    password: str,
    vcc: GeneratedVCC,
    headless: bool = False,
    use_api_email: bool = False,
    proxy: Optional[ProxyConfig] = None,
) -> Optional[str]:
    """
    Jalankan 1 siklus bot.  Return offer link string atau None.
    """
    tag = f"[Thread-{thread_id}]"
    driver: Optional[uc.Chrome] = None
    email: Optional[str] = None
    profile_path: Optional[str] = None

    try:
        # ── Generate data ────────────────────────────────────────
        email = create_temp_email(use_api_email)
        full_name = generate_random_name()

        print(f"{tag} 📧 Email: {email}")
        print(f"{tag} 👤 Nama: {full_name}")
        print(f"{tag} 💳 VCC: {vcc.formatted} | Exp: {vcc.expiry} | CVC: {vcc.cvc} | {vcc.network} [{vcc.source}]")
        if proxy:
            print(f"{tag} 🌐 Proxy: {proxy.display}")

        # ── Fresh profile ────────────────────────────────────────
        profile_path = create_profile_dir(thread_id)
        print(f"{tag} 🔒 Fresh profile: {os.path.basename(profile_path)}")

        # ── Anti-detect fingerprint ──────────────────────────────
        screen = random_from(SCREEN_SIZES)
        browser_path, browser_name = find_browser_path()

        options = uc.ChromeOptions()
        options.binary_location = browser_path
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-features=AutomationControlled,AttributionReportingCrossAppWeb")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-component-update")
        options.add_argument(f"--window-size={screen[0]},{screen[1]}")

        # ── Proxy extension ──────────────────────────────────
        proxy_ext_path = None
        if proxy:
            proxy_ext_path = create_proxy_auth_extension(proxy, thread_id)
            options.add_argument(f"--load-extension={proxy_ext_path}")
            print(f"{tag} 🔌 Proxy extension loaded: {os.path.basename(proxy_ext_path)}")

        if headless:
            options.add_argument("--headless=new")

        print(f"{tag} 🚀 Launching {browser_name} via undetected-chromedriver...")
        # Lock supaya hanya 1 thread yang patch/launch chromedriver bersamaan
        # (undetected_chromedriver patcher tidak thread-safe di Windows)
        with _chrome_launch_lock:
            driver = uc.Chrome(options=options, headless=headless, use_subprocess=True)

        # Default waits
        driver.implicitly_wait(5)
        driver.set_page_load_timeout(60)

        # Inject stealth JS
        stealth_js = build_stealth_js()
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})

        print(f"{tag} 🛡️ {browser_name} (undetected) | {screen[0]}x{screen[1]}")

        # ═══════════════════════════════════════════════════════
        #  STEP 1 — Langsung ke Coursera specialization
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 🌐 Step 1: Membuka Coursera AI Essentials...")
        try:
            driver.get("https://www.coursera.org/google-specializations/ai-essentials-gwg")
            random_delay(3000, 5000)
        except Exception as e:
            print(f"{tag} ⚠️ Specialization gagal: {e}, fallback ke course...")
            try:
                driver.get("https://www.coursera.org/learn/google-ai-essentials")
                random_delay(3000, 5000)
            except Exception as e2:
                save_screenshot(driver, tag, "err-load")
                raise e2

        # ═══════════════════════════════════════════════════════
        #  STEP 2 — (dilewati — langsung Coursera)
        # ═══════════════════════════════════════════════════════
        print(f"{tag} ℹ️ Step 2 dilewati (langsung Coursera)")

        # ═══════════════════════════════════════════════════════
        #  STEP 3 — "Enroll for free"
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 📚 Step 3: Klik 'Enroll for free'...")
        print(f"{tag} 📍 URL: {driver.current_url}")

        # Jika specialization, redirect ke course
        if "specialization" in driver.current_url or "gwg" in driver.current_url:
            print(f"{tag} 🔄 Halaman specialization, navigasi ke course...")
            driver.get("https://www.coursera.org/learn/google-ai-essentials")
            random_delay(3000, 5000)

        random_delay(2000, 4000)

        wait = WebDriverWait(driver, 30)
        enroll_btn = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//button[@data-e2e='enroll-button'] | //button[contains(text(),'Enroll for free') or contains(text(),'Enroll for Free')]"
        )))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", enroll_btn)
        random_delay(1500, 3000)
        enroll_btn.click()
        random_delay(2000, 4000)

        # ═══════════════════════════════════════════════════════
        #  STEP 4 — Email input
        # ═══════════════════════════════════════════════════════
        print(f"{tag} ✉️ Step 4: Mengisi email...")
        wait = WebDriverWait(driver, 15)
        email_input = wait.until(EC.visibility_of_element_located((
            By.CSS_SELECTOR,
            "input[name='email'], input[placeholder*='name@email'], input[placeholder*='email']"
        )))
        random_delay(800, 1500)
        email_input.click()
        email_input.clear()
        email_input.send_keys(email)
        random_delay(500, 1200)

        # Klik Continue
        continue_btn = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[contains(text(),'Continue')]"
        )))
        continue_btn.click()
        random_delay(3000, 5000)

        # ═══════════════════════════════════════════════════════
        #  STEP 5-6 — Nama & Password → "Join for Free"
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 📝 Step 5-6: Mengisi nama & password...")
        wait = WebDriverWait(driver, 15)
        name_input = wait.until(EC.visibility_of_element_located((
            By.CSS_SELECTOR,
            "input[name='fullName'], input[placeholder*='full name']"
        )))
        random_delay(500, 1200)
        name_input.click()
        name_input.send_keys(full_name)
        random_delay(500, 1000)

        pass_input = driver.find_element(By.CSS_SELECTOR, "input[name='password'], input[placeholder*='password']")
        pass_input.click()
        pass_input.send_keys(password)
        random_delay(800, 1500)

        # "Join for Free" — cari yang visible
        join_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Join for Free')]")
        join_clicked = False
        for btn in join_btns:
            if btn.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                random_delay(500, 1000)
                btn.click()
                join_clicked = True
                print(f"{tag} ✅ Klik 'Join for Free'")
                break
        if not join_clicked and join_btns:
            driver.execute_script("arguments[0].click();", join_btns[-1])

        # ═══════════════════════════════════════════════════════
        #  STEP 6-7 — Post-signup: tunggu captcha / klik "Start Free Trial"
        #  Polling setiap 2 detik, max 76 detik
        # ═══════════════════════════════════════════════════════
        print(f"{tag} ⏳ Menunggu post-signup (captcha / redirect)...")
        trial_clicked = False

        # Matikan implicit wait agar find_elements return instantly
        driver.implicitly_wait(0)

        TRIAL_XPATHS = [
            # Case-insensitive via translate — cari di semua child text (normalize-space(.))
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'start free trial')]",
            "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'start free trial')]",
            # Tombol di dalam modal Coursera
            "//div[contains(@class, 'modal')]//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'free trial')]",
            "//div[contains(@class, 'Modal')]//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'free trial')]",
            # Span di dalam button
            "//button[.//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'start free trial')]]",
            # Fallback: cari substring "free trial" saja
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'free trial')]",
        ]

        for poll in range(38):  # 38 x 2s = 76 detik max
            time.sleep(2)

            # --- Cek "I accept" (ToU modal) dulu ---
            try:
                tou_btns = driver.find_elements(By.XPATH, "//button[contains(normalize-space(.), 'I accept')]")
                for btn in tou_btns:
                    if btn.is_displayed():
                        print(f"{tag} 📋 ToU modal, klik 'I accept'...")
                        random_delay(500, 1000)
                        try:
                            btn.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", btn)
                        random_delay(2000, 3000)
                        print(f"{tag} ✅ ToU accepted")
                        break
            except Exception:
                pass

            # --- Cek "Start Free Trial" ---
            for sel in TRIAL_XPATHS:
                try:
                    btns = driver.find_elements(By.XPATH, sel)
                    for btn in btns:
                        try:
                            if btn.is_displayed() and btn.is_enabled():
                                print(f"{tag} 🆓 Step 6: Tombol 'Start Free Trial' ditemukan!")
                                random_delay(500, 1200)
                                try:
                                    btn.click()
                                except (ElementClickInterceptedException, ElementNotInteractableException):
                                    driver.execute_script("arguments[0].click();", btn)
                                trial_clicked = True
                                print(f"{tag} ✅ 'Start Free Trial' berhasil diklik!")
                                break
                        except StaleElementReferenceException:
                            continue
                except Exception:
                    pass
                if trial_clicked:
                    break

            if trial_clicked:
                break

            # --- Cek redirect ke checkout ---
            try:
                cur = driver.current_url.lower()
                if "checkout" in cur or "cart" in cur:
                    print(f"{tag} 🛒 Sudah redirect ke checkout, skip trial button")
                    trial_clicked = True
                    break
            except Exception:
                pass

            if poll % 5 == 4:
                print(f"{tag} ⏳ Masih menunggu... ({(poll + 1) * 2}s)")

        # --- Fallback: scan semua button di halaman ---
        if not trial_clicked:
            print(f"{tag} 🆓 Step 7: Fallback — scan semua button...")
            try:
                all_buttons = driver.find_elements(By.TAG_NAME, "button")
                for btn in all_buttons:
                    try:
                        txt = btn.text.strip().lower()
                        if btn.is_displayed() and ("trial" in txt or ("start" in txt and "free" in txt)):
                            print(f"{tag} 🖱️ Fallback klik: '{btn.text.strip()}'")
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                            random_delay(300, 800)
                            driver.execute_script("arguments[0].click();", btn)
                            trial_clicked = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if not trial_clicked:
            print(f"{tag} ℹ️ 'Start Free Trial' tidak ditemukan setelah 76s, lanjut ke checkout...")
        else:
            print(f"{tag} ✅ 'Start Free Trial' berhasil diklik")

        # Kembalikan implicit wait
        driver.implicitly_wait(5)
        random_delay(2000, 4000)

        # ═══════════════════════════════════════════════════════
        #  STEP 8 — Checkout: pilih Indonesia
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 🇮🇩 Step 8: Memilih negara Indonesia...")

        # Tunggu checkout page fully loaded sebelum interaksi
        # (penting untuk multi-thread di mana page load lebih lambat)
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        random_delay(3000, 5000)

        country_selected = False

        # ── Metode 1: React-Select (cc-country) ──
        # HTML: <div class="Select-input"><input id="cc-country" aria-autocomplete="list">
        if not country_selected:
            try:
                # Klik wrapper Select-input agar dropdown aktif
                react_input = driver.find_element(By.CSS_SELECTOR,
                    "input#cc-country, input[data-e2e='country']")
                if react_input.is_displayed():
                    # Klik parent div.Select-input supaya fokus
                    try:
                        wrapper = react_input.find_element(By.XPATH, "./ancestor::div[contains(@class,'Select-input')]")
                        wrapper.click()
                    except Exception:
                        react_input.click()
                    random_delay(500, 800)

                    # Ketik "Indonesia" pelan-pelan supaya autocomplete muncul
                    react_input.clear()
                    for char in "Indonesia":
                        react_input.send_keys(char)
                        random_delay(80, 150)
                    random_delay(1500, 2500)

                    # Tunggu dan klik opsi dari React-Select dropdown
                    react_option_xpaths = [
                        "//*[contains(@class,'Select-option')][contains(.,'Indonesia')]",
                        "//*[contains(@class,'Select-menu')]//*[contains(.,'Indonesia')]",
                        "//*[@id='react-select-cc-country--option-0']",
                        "//*[@role='option'][contains(.,'Indonesia')]",
                        "//*[@role='listbox']//*[contains(.,'Indonesia')]",
                        "//div[contains(@class,'option')][contains(.,'Indonesia')]",
                    ]
                    for opt_xpath in react_option_xpaths:
                        try:
                            indo_opt = WebDriverWait(driver, 3).until(
                                EC.element_to_be_clickable((By.XPATH, opt_xpath))
                            )
                            indo_opt.click()
                            country_selected = True
                            print(f"{tag} ✅ Country Indonesia dipilih (React-Select)")
                            break
                        except (TimeoutException, Exception):
                            continue

                    # Fallback: tekan Arrow Down + Enter
                    if not country_selected:
                        from selenium.webdriver.common.keys import Keys as K
                        react_input.send_keys(K.ARROW_DOWN)
                        random_delay(300, 500)
                        react_input.send_keys(K.RETURN)
                        country_selected = True
                        print(f"{tag} ✅ Country Indonesia dipilih (Arrow+Enter)")
            except (NoSuchElementException, Exception):
                pass

        # ── Metode 2: <select> tag biasa ──
        if not country_selected:
            try:
                selects = driver.find_elements(By.TAG_NAME, "select")
                for sel in selects:
                    try:
                        select_obj = Select(sel)
                        select_obj.select_by_visible_text("Indonesia")
                        country_selected = True
                        print(f"{tag} ✅ Country Indonesia dipilih (<select>)")
                        break
                    except Exception:
                        continue
            except Exception:
                pass

        # ── Metode 3: Klik placeholder "Select your country" ──
        if not country_selected:
            try:
                placeholders = driver.find_elements(By.XPATH,
                    "//*[contains(@class,'Select-placeholder')][contains(.,'country')] "
                    "| //*[contains(@class,'Select-placeholder')][contains(.,'Country')] "
                    "| //*[contains(text(),'Select your country')]"
                )
                for ph in placeholders:
                    if ph.is_displayed():
                        ph.click()
                        random_delay(500, 800)
                        break
                # Ketik di input yang muncul
                react_input2 = driver.find_element(By.CSS_SELECTOR,
                    "input#cc-country, input[data-e2e='country'], .Select-input input")
                react_input2.send_keys("Indonesia")
                random_delay(1500, 2500)
                # Klik opsi
                try:
                    opt = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH,
                            "//*[contains(@class,'Select-option')][contains(.,'Indonesia')] "
                            "| //*[@role='option'][contains(.,'Indonesia')]"
                        ))
                    )
                    opt.click()
                    country_selected = True
                    print(f"{tag} ✅ Country Indonesia dipilih (placeholder click)")
                except TimeoutException:
                    react_input2.send_keys(Keys.RETURN)
                    country_selected = True
                    print(f"{tag} ✅ Country Indonesia diketik + Enter")
            except Exception:
                pass

        # ── Metode 4: Generic input fallback ──
        if not country_selected:
            try:
                country_inputs = driver.find_elements(By.XPATH,
                    "//input[contains(@name,'country') or contains(@id,'country') "
                    "or contains(@placeholder,'Country') or contains(@aria-label,'Country') "
                    "or contains(@data-testid,'country') or contains(@data-e2e,'country')]"
                )
                for inp in country_inputs:
                    if inp.is_displayed():
                        inp.click()
                        random_delay(300, 600)
                        inp.clear()
                        for char in "Indonesia":
                            inp.send_keys(char)
                            random_delay(80, 150)
                        random_delay(1500, 2500)
                        try:
                            indo_option = WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable((By.XPATH,
                                    "//*[contains(@class,'option')][contains(.,'Indonesia')] "
                                    "| //*[@role='option'][contains(.,'Indonesia')] "
                                    "| //li[contains(.,'Indonesia')]"
                                ))
                            )
                            indo_option.click()
                            country_selected = True
                            print(f"{tag} ✅ Country Indonesia dipilih (generic)")
                        except TimeoutException:
                            inp.send_keys(Keys.RETURN)
                            country_selected = True
                            print(f"{tag} ✅ Country Indonesia diketik + Enter (generic)")
                        break
            except Exception:
                pass

        if not country_selected:
            print(f"{tag} ⚠️ Country Indonesia gagal dipilih, lanjut...")

        random_delay(1000, 2000)

        # ═══════════════════════════════════════════════════════
        #  STEP 9 — Isi VCC (Braintree / Stripe / Direct)
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 💳 Step 9: Mengisi data VCC...")

        # Tunggu checkout form stabil (iframe payment butuh waktu load)
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        random_delay(4000, 6000)

        # Log iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"{tag} 🔍 Total iframes: {len(iframes)}")
        for ifr in iframes:
            src = ifr.get_attribute("src") or ""
            name = ifr.get_attribute("name") or ""
            if src and "about:blank" not in src:
                print(f"{tag}    ↳ {name}  src={src[:100]}")

        payment_filled = False

        # ── METODE 1: Braintree Hosted Fields ──
        if not payment_filled:
            try:
                print(f"{tag} 🔍 Coba Braintree Hosted Fields...")
                bt_iframes = [f for f in iframes
                              if ("braintree" in (f.get_attribute("src") or "").lower()
                                  or "braintreegateway" in (f.get_attribute("src") or "").lower())]

                if bt_iframes:
                    print(f"{tag} ✅ Braintree terdeteksi! ({len(bt_iframes)} frame)")

                    for frame in bt_iframes:
                        src = (frame.get_attribute("src") or "").lower()
                        driver.switch_to.frame(frame)
                        inp = None
                        try:
                            inp = driver.find_element(By.TAG_NAME, "input")
                        except NoSuchElementException:
                            driver.switch_to.default_content()
                            continue

                        if "card-number" in src or "credit-card" in src:
                            print(f"{tag} 💳 [BT] Card number...")
                            human_type(inp, vcc.number.replace(" ", ""))
                        elif "expiration" in src or "exp" in src:
                            print(f"{tag} 📅 [BT] Expiry...")
                            human_type(inp, vcc.exp_month + vcc.exp_year)
                        elif "cvv" in src or "cvc" in src or "security" in src:
                            print(f"{tag} 🔒 [BT] CVV...")
                            human_type(inp, vcc.cvc)

                        random_delay(300, 600)
                        driver.switch_to.default_content()

                    payment_filled = True
                    print(f"{tag} ✅ VCC diisi via Braintree!")
            except Exception as e:
                print(f"{tag} ⚠️ Braintree gagal: {e}")
                driver.switch_to.default_content()

        # ── METODE 2: Stripe Payment Element (1 iframe) ──
        if not payment_filled:
            try:
                print(f"{tag} 🔍 Coba Stripe Payment Element...")
                # Refresh iframes — bisa berubah setelah checkout load
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                stripe_frames = [f for f in iframes
                                 if any(x in (f.get_attribute("src") or "").lower()
                                        for x in ["stripe.com", "js.stripe.com"])
                                 or "stripe" in (f.get_attribute("name") or "").lower()]

                for frame in stripe_frames:
                    driver.switch_to.frame(frame)
                    try:
                        card_inp = WebDriverWait(driver, 5).until(
                            EC.visibility_of_element_located((By.CSS_SELECTOR,
                                "input[name='number'], input[autocomplete='cc-number'], "
                                "input[placeholder*='1234'], input[data-elements-stable-field-name='cardNumber']"
                            ))
                        )
                        print(f"{tag} ✅ Stripe terdeteksi!")
                        print(f"{tag} 💳 [Stripe] Card number...")
                        human_type(card_inp, vcc.number.replace(" ", ""))
                        random_delay(500, 1000)

                        exp_inp = driver.find_element(By.CSS_SELECTOR,
                            "input[name='expiry'], input[autocomplete='cc-exp'], "
                            "input[placeholder*='MM'], input[data-elements-stable-field-name='cardExpiry']"
                        )
                        print(f"{tag} 📅 [Stripe] Expiry...")
                        human_type(exp_inp, vcc.exp_month + vcc.exp_year)
                        random_delay(500, 1000)

                        cvc_inp = driver.find_element(By.CSS_SELECTOR,
                            "input[name='cvc'], input[autocomplete='cc-csc'], "
                            "input[placeholder*='CVC'], input[data-elements-stable-field-name='cardCvc']"
                        )
                        print(f"{tag} 🔒 [Stripe] CVC...")
                        human_type(cvc_inp, vcc.cvc)

                        payment_filled = True
                        print(f"{tag} ✅ VCC diisi via Stripe!")
                        break
                    except (TimeoutException, NoSuchElementException):
                        pass
                    finally:
                        driver.switch_to.default_content()
            except Exception as e:
                print(f"{tag} ⚠️ Stripe gagal: {e}")
                driver.switch_to.default_content()

        # ── METODE 3: Stripe Elements (multi-iframe lama) ──
        if not payment_filled:
            try:
                print(f"{tag} 🔍 Coba Stripe Elements multi-iframe...")
                stripe_frames = [f for f in iframes if "stripe.com" in (f.get_attribute("src") or "")]
                print(f"{tag} ℹ️ Stripe frames: {len(stripe_frames)}")

                for frame in stripe_frames:
                    driver.switch_to.frame(frame)
                    try:
                        card_el = driver.find_element(By.CSS_SELECTOR,
                            "input[name='cardnumber'], input[name='number'], input[autocomplete='cc-number']"
                        )
                        if card_el.is_displayed():
                            human_type(card_el, vcc.number.replace(" ", ""))
                            payment_filled = True
                    except NoSuchElementException:
                        pass
                    try:
                        exp_el = driver.find_element(By.CSS_SELECTOR,
                            "input[name='exp-date'], input[name='expiry'], input[autocomplete='cc-exp']"
                        )
                        if exp_el.is_displayed():
                            human_type(exp_el, vcc.exp_month + vcc.exp_year)
                    except NoSuchElementException:
                        pass
                    try:
                        cvc_el = driver.find_element(By.CSS_SELECTOR,
                            "input[name='cvc'], input[autocomplete='cc-csc']"
                        )
                        if cvc_el.is_displayed():
                            human_type(cvc_el, vcc.cvc)
                    except NoSuchElementException:
                        pass
                    driver.switch_to.default_content()

                if payment_filled:
                    print(f"{tag} ✅ VCC diisi via Stripe Elements (multi-iframe)!")
            except Exception as e:
                print(f"{tag} ⚠️ Stripe Elements gagal: {e}")
                driver.switch_to.default_content()

        # ── METODE 4: Direct input (tanpa iframe) ──
        if not payment_filled:
            try:
                print(f"{tag} 🔍 Coba direct input...")
                card_direct = WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR,
                        "input[autocomplete='cc-number'], input[name*='card'], "
                        "input[id*='card-number'], input[data-testid*='card']"
                    ))
                )
                print(f"{tag} 💳 [Direct] Card number...")
                human_type(card_direct, vcc.number.replace(" ", ""))
                random_delay(500, 800)

                try:
                    exp_d = driver.find_element(By.CSS_SELECTOR,
                        "input[autocomplete='cc-exp'], input[name*='exp'], input[id*='expir']"
                    )
                    human_type(exp_d, f"{vcc.exp_month}/{vcc.exp_year}")
                except NoSuchElementException:
                    pass
                try:
                    cvc_d = driver.find_element(By.CSS_SELECTOR,
                        "input[autocomplete='cc-csc'], input[name*='cvc'], input[name*='cvv'], "
                        "input[id*='cvc'], input[id*='cvv']"
                    )
                    human_type(cvc_d, vcc.cvc)
                except NoSuchElementException:
                    pass

                payment_filled = True
                print(f"{tag} ✅ VCC diisi via direct input!")
            except Exception as e:
                print(f"{tag} ⚠️ Direct input gagal: {e}")

        if not payment_filled:
            print(f"{tag} ❌ Tidak ada payment form terdeteksi!")
            save_screenshot(driver, tag, "err-payment")

        random_delay(2000, 4000)

        # ═══════════════════════════════════════════════════════
        #  STEP 10 — Submit payment "Start Free Trial"
        # ═══════════════════════════════════════════════════════
        print(f"{tag} ⏬ Step 10: Submit payment...")
        driver.execute_script("window.scrollBy(0, 500);")
        random_delay(2000, 4000)

        submit_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[contains(text(),'Start Free Trial') or contains(text(),'Start free trial')] "
                "| //button[@type='submit']"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
        random_delay(1500, 3000)
        submit_btn.click()

        # Smart wait (max 90s): tunggu URL berubah dari checkout
        print(f"{tag} ⏳ Menunggu proses pembayaran (max 90s)...")
        try:
            WebDriverWait(driver, 90).until(
                lambda d: "checkout" not in d.current_url
            )
            print(f"{tag} ✅ Redirect: {driver.current_url}")
        except TimeoutException:
            print(f"{tag} ⚠️ Tidak ada redirect, lanjut...")
        random_delay(3000, 5000)

        # ═══════════════════════════════════════════════════════
        #  STEP 11 — "My commitment" page
        # ═══════════════════════════════════════════════════════
        print(f"{tag} ✅ Step 11: 'My commitment'...")
        random_delay(2000, 4000)

        try:
            # Cari checkbox — coba beberapa selector
            commit_cb = None
            for sel in [
                "//input[@type='checkbox'][ancestor::*[contains(.,'I commit')]]",
                "//input[@type='checkbox']",
            ]:
                try:
                    commit_cb = WebDriverWait(driver, 12).until(
                        EC.presence_of_element_located((By.XPATH, sel))
                    )
                    if commit_cb:
                        break
                except TimeoutException:
                    continue

            if commit_cb:
                random_delay(800, 1500)
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", commit_cb)
                random_delay(300, 600)
                # Cek apakah sudah tercentang
                is_checked = commit_cb.is_selected() or driver.execute_script(
                    "return arguments[0].checked || arguments[0].getAttribute('aria-checked') === 'true';", commit_cb
                )
                if not is_checked:
                    print(f"{tag} 🖱️ Click: Commit checkbox")
                    try:
                        commit_cb.click()
                    except (ElementClickInterceptedException, ElementNotInteractableException):
                        # JS click sebagai fallback
                        driver.execute_script("arguments[0].click();", commit_cb)
                    random_delay(500, 1000)
                    # Verifikasi checkbox tercentang
                    is_now = commit_cb.is_selected() or driver.execute_script(
                        "return arguments[0].checked;", commit_cb
                    )
                    if not is_now:
                        # Force via JS property
                        driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", commit_cb)
                    print(f"{tag} ✅ Checkbox tercentang")
                else:
                    print(f"{tag} ✅ Checkbox sudah tercentang")
            else:
                print(f"{tag} ⚠️ Checkbox tidak ditemukan")

            random_delay(500, 1200)

            # Klik "Start the course" — button bisa punya <span class="cds-button-label">Start the course</span>
            start_course_btn = None
            for sc_sel in [
                "//button[contains(normalize-space(.), 'Start the course')]",
                "//button[.//span[contains(text(), 'Start the course')]]",
                "//button[contains(@class, 'cds-button')][contains(., 'Start')]",
                "//button[contains(text(), 'Start the course')]",
            ]:
                try:
                    start_course_btn = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, sc_sel))
                    )
                    if start_course_btn and start_course_btn.is_displayed():
                        break
                except TimeoutException:
                    continue

            if start_course_btn:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", start_course_btn)
                random_delay(800, 1500)
                print(f"{tag} 🖱️ Click: Start the course")
                try:
                    start_course_btn.click()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    driver.execute_script("arguments[0].click();", start_course_btn)
            else:
                print(f"{tag} ⚠️ 'Start the course' button tidak ditemukan")
            random_delay(3000, 5000)
        except TimeoutException:
            print(f"{tag} ℹ️ Tidak ada 'My commitment', lanjut...")
        except Exception as e:
            print(f"{tag} ⚠️ Step 11 error: {e} — lanjut...")
            save_screenshot(driver, tag, "err-step11")

        # ═══════════════════════════════════════════════════════
        #  STEP 12 — Success popup
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 🎉 Step 12: Popup success...")
        random_delay(2000, 4000)

        # Coba klik tombol di dalam modal success (cds-Modal-container)
        popup_closed = False
        for attempt in range(1, 4):
            try:
                # Cek apakah ada modal visible
                modals = driver.find_elements(By.CSS_SELECTOR, ".cds-Modal-container")
                visible_modal = None
                for m in modals:
                    try:
                        if m.is_displayed():
                            visible_modal = m
                            break
                    except Exception:
                        continue

                if not visible_modal:
                    print(f"{tag} ℹ️ Tidak ada modal popup visible")
                    break

                print(f"{tag} 🔍 Modal terdeteksi (attempt {attempt}), cari tombol...")

                # Cari tombol di dalam modal
                btn_found = False
                for btn_text in ["Continue", "Continue learning", "Go to course", "Start learning"]:
                    try:
                        btns = visible_modal.find_elements(By.XPATH, f".//button[contains(.,'{btn_text}')]")
                        for b in btns:
                            if b.is_displayed():
                                print(f"{tag} 🖱️ Click: '{btn_text}' di popup")
                                try:
                                    b.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", b)
                                btn_found = True
                                random_delay(1000, 2000)
                                break
                    except Exception:
                        continue
                    if btn_found:
                        break

                if not btn_found:
                    # Fallback: klik button pertama yang visible di modal
                    try:
                        any_btns = visible_modal.find_elements(By.TAG_NAME, "button")
                        for ab in any_btns:
                            if ab.is_displayed() and ab.is_enabled():
                                print(f"{tag} 🖱️ Click: button fallback di modal")
                                driver.execute_script("arguments[0].click();", ab)
                                btn_found = True
                                random_delay(1000, 2000)
                                break
                    except Exception:
                        pass

                if not btn_found:
                    # Last resort: close via ESC
                    print(f"{tag} 🖱️ Tidak ada tombol, coba ESC...")
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    random_delay(500, 1000)

                # Tunggu modal hilang
                try:
                    WebDriverWait(driver, 5).until_not(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, ".cds-Modal-container"))
                    )
                    popup_closed = True
                    break
                except TimeoutException:
                    print(f"{tag} ⚠️ Modal masih visible setelah klik (attempt {attempt})")

            except Exception as e:
                print(f"{tag} ⚠️ Popup handling error (attempt {attempt}): {e}")

        # Nuclear option: hapus semua modal dari DOM via JavaScript
        if not popup_closed:
            try:
                removed = driver.execute_script("""
                    var modals = document.querySelectorAll('.cds-Modal-container, .cds-Modal-backdrop, [class*="Modal-backdrop"], [class*="modal-backdrop"]');
                    var count = 0;
                    modals.forEach(function(m) { m.remove(); count++; });
                    // Also remove overflow:hidden from body
                    document.body.style.overflow = '';
                    document.body.style.position = '';
                    document.documentElement.style.overflow = '';
                    return count;
                """)
                if removed:
                    print(f"{tag} 🗑️ Removed {removed} modal element(s) from DOM via JS")
            except Exception as e:
                print(f"{tag} ⚠️ JS modal removal gagal: {e}")

        random_delay(2000, 3500)

        # ═══════════════════════════════════════════════════════
        #  STEP 13 — Module 2
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 📖 Step 13: Memilih Module 2...")
        random_delay(3000, 5000)

        # Pastikan tidak ada overlay/modal yang menghalangi
        try:
            driver.execute_script("""
                document.querySelectorAll('.cds-Modal-container, .cds-Modal-backdrop, [class*="Modal-backdrop"], [class*="modal-backdrop"]')
                    .forEach(function(m) { m.remove(); });
                document.body.style.overflow = '';
                document.body.style.position = '';
                document.documentElement.style.overflow = '';
            """)
        except Exception:
            pass
        random_delay(500, 1000)

        mod2_clicked = False
        for mod2_attempt in range(1, 4):
            try:
                mod2 = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Module 2')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", mod2)
                random_delay(500, 1000)

                # Coba normal click dulu
                try:
                    mod2.click()
                    mod2_clicked = True
                    break
                except ElementClickInterceptedException:
                    print(f"{tag} ⚠️ Module 2 click intercepted (attempt {mod2_attempt}), hapus overlay...")
                    # Hapus semua overlay
                    driver.execute_script("""
                        document.querySelectorAll('.cds-Modal-container, .cds-Modal-backdrop, [class*="Modal"], [class*="modal"][class*="backdrop"]')
                            .forEach(function(m) { m.remove(); });
                        document.body.style.overflow = '';
                    """)
                    random_delay(500, 1000)
                    # Retry via JS click
                    try:
                        driver.execute_script("arguments[0].click();", mod2)
                        mod2_clicked = True
                        break
                    except Exception:
                        random_delay(1000, 2000)
                except (ElementNotInteractableException, StaleElementReferenceException):
                    random_delay(1000, 2000)

            except TimeoutException:
                print(f"{tag} ⚠️ Module 2 tidak ditemukan (attempt {mod2_attempt}), scroll...")
                driver.execute_script("window.scrollBy(0, 400);")
                random_delay(1000, 2000)

        if mod2_clicked:
            print(f"{tag} ✅ Module 2 clicked")
        else:
            print(f"{tag} ⚠️ Module 2 click gagal setelah 3 attempt, lanjut...")
        random_delay(2000, 3000)

        # Scroll sidebar
        try:
            sidebar = driver.find_element(By.CSS_SELECTOR,
                "[class*='sidebar'], [class*='rail'], [role='navigation']"
            )
            driver.execute_script("arguments[0].scrollBy(0, 600);", sidebar)
        except Exception:
            driver.execute_script("window.scrollBy(0, 500);")
        random_delay(1500, 2500)

        # ═══════════════════════════════════════════════════════
        #  STEP 14 — "Redeem your Google AI Pro trial"
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 🎁 Step 14: Klik 'Redeem your Google AI Pro trial'...")
        redeem_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH,
                "//*[contains(text(),'Redeem your Google AI Pro trial')]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", redeem_link)
        random_delay(1000, 2000)
        redeem_link.click()
        random_delay(3000, 5000)

        # ═══════════════════════════════════════════════════════
        #  STEP 15-16 — Agree → Launch App
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 🚀 Step 15-16: Agree & Launch App...")
        random_delay(2000, 3000)

        # ── Scroll panel kanan Coursera (bukan window) ──
        # Coursera punya scrollable container di sisi kanan; window.scrollBy
        # hanya scroll outer window. Kita harus scroll SEMUA container yang
        # punya overflow auto/scroll.
        def scroll_all_containers_to_bottom():
            """Scroll window + semua scrollable div ke bawah."""
            driver.execute_script("""
                // Scroll window
                window.scrollTo(0, document.body.scrollHeight);

                // Cari semua elemen dengan overflow scroll/auto
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    var style = window.getComputedStyle(el);
                    var oy = style.overflowY;
                    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 50) {
                        el.scrollTop = el.scrollHeight;
                    }
                }

                // Coursera-specific containers
                var selectors = [
                    '[class*="rc-LtiLauncher"]',
                    '[class*="ItemPage"]',
                    '[class*="content-container"]',
                    '[class*="rc-DesktopLayout"]',
                    '[role="main"]',
                    'main',
                    '[class*="styled-scroll"]',
                    '[class*="item-page-content"]',
                    '[data-testid="item-page-content"]'
                ];
                selectors.forEach(function(sel) {
                    try {
                        var els = document.querySelectorAll(sel);
                        els.forEach(function(c) {
                            c.scrollTop = c.scrollHeight;
                        });
                    } catch(e) {}
                });
            """)

        # Scroll beberapa kali dengan jeda
        for scroll_i in range(8):
            scroll_all_containers_to_bottom()
            random_delay(800, 1200)
            # Cek apakah checkbox/Launch App sudah visible
            try:
                cbs = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                for cb in cbs:
                    if cb.is_displayed():
                        break
                else:
                    continue
                break  # checkbox visible, stop scrolling
            except Exception:
                continue

        # Tambahan: scroll khusus ke elemen target via scrollIntoView
        try:
            driver.execute_script("""
                // Coba scrollIntoView langsung ke area tool-launch / HonorCodeAgreement
                var targets = document.querySelectorAll(
                    '.tool-launch, .rc-HonorCodeAgreement, .rc-LtiVerifyAndLaunch, ' +
                    '[class*="agreement"], input[type="checkbox"], ' +
                    'button[aria-label*="Launch"], button[type="submit"]'
                );
                if (targets.length > 0) {
                    targets[targets.length - 1].scrollIntoView({behavior: 'smooth', block: 'center'});
                }
            """)
            random_delay(1500, 2000)
        except Exception:
            pass

        # ── Checkbox "I agree to use this app responsibly." ──
        agree_found = False
        try:
            driver.implicitly_wait(0)

            # Selector berbasis HTML: input[value='agree'], atau ancestor "I agree"
            cb_selectors = [
                "input[value='agree']",
                "input[type='checkbox'][value='agree']",
                ".rc-HonorCodeAgreement input[type='checkbox']",
                ".agreement-container input[type='checkbox']",
            ]
            cb_xpaths = [
                "//input[@type='checkbox'][ancestor::*[contains(@class,'HonorCode')]]",
                "//input[@type='checkbox'][ancestor::*[contains(@class,'agreement')]]",
                "//input[@type='checkbox'][ancestor::*[contains(.,'I agree')]]",
                "//label[contains(.,'I agree')]//input[@type='checkbox']",
                "//input[@type='checkbox']",
            ]

            # Coba CSS selector dulu (lebih cepat)
            for css_sel in cb_selectors:
                if agree_found:
                    break
                try:
                    cbs = driver.find_elements(By.CSS_SELECTOR, css_sel)
                    for cb in cbs:
                        if cb.is_displayed() or True:  # force try even if 'hidden'
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", cb)
                            random_delay(500, 800)
                            if not cb.is_selected():
                                try:
                                    cb.click()
                                except (ElementClickInterceptedException,
                                        ElementNotInteractableException):
                                    driver.execute_script("arguments[0].click();", cb)
                            agree_found = True
                            print(f"{tag} ✅ Checkbox agree tercentang (CSS: {css_sel})")
                            break
                except Exception:
                    continue

            # Coba XPath
            if not agree_found:
                for xp in cb_xpaths:
                    if agree_found:
                        break
                    try:
                        cbs = driver.find_elements(By.XPATH, xp)
                        for cb in cbs:
                            if cb.is_displayed() or True:
                                driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center'});", cb)
                                random_delay(500, 800)
                                if not cb.is_selected():
                                    try:
                                        cb.click()
                                    except (ElementClickInterceptedException,
                                            ElementNotInteractableException):
                                        driver.execute_script("arguments[0].click();", cb)
                                agree_found = True
                                print(f"{tag} ✅ Checkbox agree tercentang (XPath)")
                                break
                    except Exception:
                        continue

            driver.implicitly_wait(5)

            if not agree_found:
                # Fallback: tunggu pakai WebDriverWait
                agree_cb = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "input[type='checkbox'][value='agree'], "
                        ".rc-HonorCodeAgreement input[type='checkbox'], "
                        "input[type='checkbox']"))
                )
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", agree_cb)
                random_delay(800, 1500)
                if not agree_cb.is_selected():
                    try:
                        agree_cb.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", agree_cb)
                agree_found = True
                print(f"{tag} ✅ Checkbox agree tercentang (WebDriverWait fallback)")
        except Exception:
            print(f"{tag} ⚠️ Checkbox agree tidak ditemukan...")

        random_delay(500, 1200)

        # ── Tombol "Launch App" ──
        # HTML: <button type="submit" aria-label="Launch app. Opens in new window">
        #         <span class="cds-button-label">Launch App ...</span>
        #       </button>
        try:
            launch_selectors = [
                "button[aria-label*='Launch app']",
                "button[aria-label*='Launch App']",
                "button[type='submit'] .cds-button-label",
                ".tool-launch button[type='submit']",
                ".rc-LtiVerifyAndLaunch button[type='submit']",
            ]
            launch_btn = None
            for lsel in launch_selectors:
                try:
                    launch_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, lsel))
                    )
                    break
                except (TimeoutException, Exception):
                    continue

            # Fallback XPath
            if not launch_btn:
                launch_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                        "//button[contains(normalize-space(.),'Launch App')] "
                        "| //button[.//span[contains(text(),'Launch App')]] "
                        "| //button[@aria-label[contains(.,'Launch')]] "
                        "| //a[contains(normalize-space(.),'Launch App')]"
                    ))
                )

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", launch_btn)
            random_delay(800, 1500)
            try:
                launch_btn.click()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                driver.execute_script("arguments[0].click();", launch_btn)
            print(f"{tag} 🚀 Launch App diklik")
            random_delay(2000, 4000)
        except TimeoutException:
            print(f"{tag} ⚠️ 'Launch App' tidak ditemukan, lanjut...")

        # ═══════════════════════════════════════════════════════
        #  STEP 17-18 — Extract offer link
        # ═══════════════════════════════════════════════════════
        print(f"{tag} 🔗 Step 17-18: Mengambil link offer...")

        OFFER_RE = re.compile(r"https://one\.google\.com/offer/(?!terms)[A-Za-z0-9]{10,}")
        offer_link: Optional[str] = None

        def extract_from_page() -> Optional[str]:
            """Try extract offer link from current page."""
            # Method 1: via <a> tags
            try:
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='one.google.com/offer/']")
                for lnk in links:
                    href = lnk.get_attribute("href") or ""
                    if OFFER_RE.search(href) and "terms-and-conditions" not in href:
                        return OFFER_RE.search(href).group(0)
            except Exception:
                pass
            # Method 2: page source
            try:
                match = OFFER_RE.search(driver.page_source)
                if match:
                    return match.group(0)
            except Exception:
                pass
            return None

        # Check if new tab opened (Launch App)
        if len(driver.window_handles) > 1:
            latest_handle = driver.window_handles[-1]
            driver.switch_to.window(latest_handle)
            random_delay(3000, 5000)
            print(f"{tag} 📄 Tab terbuka: {driver.current_url}")
            offer_link = extract_from_page()

        if not offer_link:
            # Try all tabs
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                random_delay(1000, 2000)
                offer_link = extract_from_page()
                if offer_link:
                    break

        # ═══════════════════════════════════════════════════════
        #  SAVE RESULT
        # ═══════════════════════════════════════════════════════
        if offer_link:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(f"{offer_link}\r\n")
            print(f"{tag} ✅ BERHASIL! Link: {offer_link}")
            print(f"{tag} 💾 Tersimpan di {OUTPUT_FILE}")

            # ☁️ Simpan ke Google Sheets
            if CLOUD_ENABLED:
                save_link_cloud(link=offer_link, email=email or "?", status="SUCCESS")
        else:
            print(f"{tag} ❌ Link offer tidak ditemukan!")
            save_screenshot(driver, tag, "err-offer")
            log_error(tag, email or "?", "Link offer tidak ditemukan")

        return offer_link

    except Exception as exc:
        print(f"{tag} ❌ Error: {exc}")
        traceback.print_exc()
        log_error(tag, email or "no-email", str(exc))
        if driver:
            save_screenshot(driver, tag, "error")
        if email:
            delete_temp_email(email, use_api_email)

        return None

    finally:
        # Cleanup
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if profile_path:
            delete_profile_dir(profile_path)
            print(f"{tag} 🗑️ Profile dihapus: {os.path.basename(profile_path)}")
        # Cleanup proxy extension folder (dibuat per-thread)
        # Note: folder di-cleanup otomatis di cleanup_proxy_extensions()


def run_bot_with_retry(
    thread_id: int,
    password: str,
    vcc: GeneratedVCC,
    headless: bool = False,
    use_api_email: bool = False,
    proxy: Optional[ProxyConfig] = None,
    get_next_proxy_fn=None,
    max_retries: int = 2,
) -> Optional[str]:
    """
    Wrapper run_bot() dengan auto-retry.
    Kalau gagal, coba ulang max_retries kali dengan proxy baru (jika tersedia).
    """
    tag = f"[Thread-{thread_id}]"
    for attempt in range(1, max_retries + 1):
        # RAM check sebelum launch
        wait_for_ram(tag)

        result = run_bot(thread_id, password, vcc, headless, use_api_email, proxy=proxy)
        if result:
            return result

        if attempt < max_retries:
            # Ambil proxy baru untuk retry (kalau ada)
            if get_next_proxy_fn:
                new_proxy = get_next_proxy_fn()
                if new_proxy:
                    proxy = new_proxy
                    print(f"{tag} 🔄 Retry {attempt}/{max_retries-1} dengan proxy baru: {proxy.display}")
                else:
                    print(f"{tag} 🔄 Retry {attempt}/{max_retries-1} (proxy tetap)")
            else:
                print(f"{tag} 🔄 Retry {attempt}/{max_retries-1}")

            # Delay sebelum retry
            delay = random.randint(5, 10)
            print(f"{tag} ⏳ Delay {delay}s sebelum retry...")
            time.sleep(delay)

    return None


# ═══════════════════════════════════════════════════════════════
#  CLI — MAIN
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    print("╔══════════════════════════════════════════╗")
    print("║   🤖 Auto Gemini AI Pro - Bot (Python)    ║")
    print("╚══════════════════════════════════════════╝")
    print()

    cleanup_all_profiles()
    cleanup_proxy_extensions()
    print("🧹 Cleaned up old browser profiles & proxy extensions")
    os.makedirs(LOGS_DIR, exist_ok=True)
    print(f"📁 Logs folder: {os.path.abspath(LOGS_DIR)}")

    # ── Cloud Storage status ──────────────────────────────
    if CLOUD_ENABLED:
        print("☁️  Cloud Storage: ✅ AKTIF — link akan disimpan ke Google Sheets")
    else:
        print("☁️  Cloud Storage: ❌ Tidak aktif (opsional — baca TUTORIAL.md)")
    print()

    # ── Mode Email ────────────────────────────────────────
    email_choice = input("Mode email: (1) Random generate  (2) API Hubify  [1/2]: ").strip()
    use_api_email = email_choice == "2"
    print(f"📧 Mode email  : {'API Hubify' if use_api_email else 'Random generate'}")
    print()

    # ── Mode VCC ──────────────────────────────────────────
    vcc_choice = input("Mode VCC: (1) Generate dari BIN  (2) Dari file vcc-list.txt  [1/2]: ").strip()
    vcc_mode = "list" if vcc_choice == "2" else "generate"

    bin_configs: List[VCCConfig] = []
    vcc_list: List[GeneratedVCC] = []
    vcc_list_index = [0]  # mutable counter for closure

    def _find_file(name: str) -> str:
        """Cari file di folder python/ dulu, kalau gak ada cek parent folder."""
        local = os.path.join(_SELF_DIR, name)
        if os.path.isfile(local):
            return local
        parent = os.path.join(_PARENT_DIR, name)
        if os.path.isfile(parent):
            return parent
        return local  # default, biar error message jelas

    if vcc_mode == "generate":
        bin_path = _find_file("bin-config.json")
        try:
            raw = json.loads(Path(bin_path).read_text(encoding="utf-8"))
            bin_array = raw if isinstance(raw, list) else [raw]
            for bd in bin_array:
                if not bd.get("bin") or not bd.get("expMonth") or not bd.get("expYear"):
                    print("⚠️ bin-config.json entry belum lengkap, skip...")
                    continue
                if not validate_bin(bd["bin"]):
                    print(f"⚠️ BIN {bd['bin']} tidak valid, skip...")
                    continue
                bin_configs.append(VCCConfig(bin=bd["bin"], exp_month=bd["expMonth"], exp_year=bd["expYear"]))
            if not bin_configs:
                print("❌ Tidak ada BIN valid di bin-config.json!")
                sys.exit(1)
            print(f"💳 BIN loaded: {len(bin_configs)} BIN(s) dari {os.path.basename(os.path.dirname(bin_path))}/")
            for i, b in enumerate(bin_configs):
                print(f"   {i+1}. {b.bin}**** ({b.exp_month}/{b.exp_year})")
        except Exception as e:
            print(f"❌ Gagal load bin-config.json: {e}")
            sys.exit(1)
    else:
        try:
            vcc_path = _find_file("vcc-list.txt")
            lines = Path(vcc_path).read_text(encoding="utf-8").splitlines()
            for line in lines:
                parsed = parse_vcc_line(line)
                if parsed:
                    vcc_list.append(parsed)
            if not vcc_list:
                print("❌ Tidak ada VCC valid di vcc-list.txt!")
                sys.exit(1)
            print(f"💳 VCC list loaded: {len(vcc_list)} kartu dari {os.path.basename(os.path.dirname(vcc_path))}/")
            for i, v in enumerate(vcc_list):
                print(f"   {i+1}. {v.formatted} | {v.expiry} | {v.network}")
        except Exception as e:
            print(f"❌ Gagal load vcc-list.txt: {e}")
            sys.exit(1)

    def get_next_vcc() -> GeneratedVCC:
        if vcc_mode == "list":
            vcc = vcc_list[vcc_list_index[0] % len(vcc_list)]
            vcc_list_index[0] += 1
            return vcc
        else:
            config = random.choice(bin_configs)
            return generate_vcc(config)

    # ── Jumlah & threads ─────────────────────────────────
    total_str = input("Jumlah akun yang mau dibuat: ").strip()
    total = int(total_str) if total_str.isdigit() else 0
    if total < 1:
        print("❌ Jumlah tidak valid!")
        sys.exit(1)

    threads_str = input(f"Jumlah thread parallel (1-{min(total, 8)}): ").strip()
    threads = max(1, min(int(threads_str) if threads_str.isdigit() else 1, min(total, 8)))

    retry_str = input("Auto-retry jika gagal (0-3) [default: 2]: ").strip()
    max_retries = max(1, min(int(retry_str) if retry_str.isdigit() else 2, 4))  # min 1 (no retry), max 4

    headless_choice = input("Mode browser: (1) Visible  (2) Headless  [1/2]: ").strip()
    headless = headless_choice == "2"

    # ── Mode IP: VPN atau Proxy ────────────────────────────
    print()
    print("Mode IP / Anonimitas:")
    print("  (0) Skip — tanpa VPN/Proxy")
    print("  (1) VPN Rotation")
    print("  (2) Proxy — dari file proxy-list.txt (mendukung 1000+ port)")
    print("  (3) Proxy — single proxy (input manual)")
    ip_choice = input("Pilih [0-3]: ").strip()

    # VPN variables
    vpn_type = "none"
    vpn_disconnect_cmd = ""
    vpn_connect_cmd = ""
    vpn_rotate_every = threads

    # Proxy variables
    proxy_mode = "none"  # none | list | single
    proxy_list: List[ProxyConfig] = []
    proxy_list_index = [0]  # mutable counter for round-robin

    if ip_choice == "1":
        # ── VPN ─────────────────────────────────────────────
        vpn_sub = input("VPN: (1) NordVPN  (2) ExpressVPN  (3) Windscribe  (4) Custom  [1-4]: ").strip()
        vpn_sub_map = {"1": "nordvpn", "2": "expressvpn", "3": "windscribe", "4": "custom"}
        vpn_type = vpn_sub_map.get(vpn_sub, "nordvpn")
        if vpn_type == "custom":
            vpn_disconnect_cmd = input("Command DISCONNECT VPN: ").strip()
            vpn_connect_cmd = input("Command CONNECT VPN: ").strip()
        every_str = input(f"Rotate VPN setiap berapa akun? [default: {threads}]: ").strip()
        vpn_rotate_every = int(every_str) if every_str.isdigit() else threads
        print(f"🔄 VPN  : {vpn_type} — rotate setiap {vpn_rotate_every} akun")

    elif ip_choice == "2":
        # ── Proxy dari file ─────────────────────────────────
        proxy_path = _find_file("proxy-list.txt")
        proxy_list = load_proxy_list(proxy_path)
        if not proxy_list:
            print("❌ Tidak ada proxy valid di proxy-list.txt!")
            print("   Format per baris: host:port:username:password")
            print(f"   Contoh: growtechcentral.com:10000:user123:pass456")
            sys.exit(1)
        proxy_mode = "list"
        print(f"🌐 Proxy loaded: {len(proxy_list)} proxy dari {os.path.basename(proxy_path)}")
        # Tampilkan 5 proxy pertama
        for i, px in enumerate(proxy_list[:5]):
            print(f"   {i+1}. {px.display}")
        if len(proxy_list) > 5:
            print(f"   ... dan {len(proxy_list) - 5} proxy lainnya")

    elif ip_choice == "3":
        # ── Single proxy ────────────────────────────────────
        proxy_str = input("Proxy (host:port:user:pass): ").strip()
        single_proxy = parse_proxy(proxy_str)
        if not single_proxy:
            print("❌ Format proxy tidak valid! Gunakan: host:port:username:password")
            sys.exit(1)
        proxy_list = [single_proxy]
        proxy_mode = "single"
        print(f"🌐 Proxy: {single_proxy.display}")

    else:
        print("🔄 Mode IP: tanpa VPN/Proxy")

    def get_next_proxy() -> Optional[ProxyConfig]:
        """Round-robin proxy dari list. Return None kalau proxy tidak aktif."""
        if proxy_mode == "none":
            return None
        px = proxy_list[proxy_list_index[0] % len(proxy_list)]
        proxy_list_index[0] += 1
        return px

    # ── Summary ───────────────────────────────────────────
    print()
    print("═══════════════════════════════════════")
    print(f"📊 Total akun  : {total}")
    print(f"🧵 Threads     : {threads}")
    print(f"🔑 Password    : Random per akun")
    print(f"📧 Mode email  : {'API Hubify' if use_api_email else 'Random generate'}")
    vcc_desc = (f"Dari file ({len(vcc_list)} kartu, round-robin)" if vcc_mode == "list"
                else f"Generate dari BIN ({len(bin_configs)} BIN)")
    print(f"💳 Mode VCC    : {vcc_desc}")
    print(f"👁️ Browser     : {'Headless' if headless else 'Visible'}")
    # IP mode summary
    if proxy_mode != "none":
        px_desc = (f"Proxy list ({len(proxy_list)} proxy, round-robin)" if proxy_mode == "list"
                   else f"Single proxy: {proxy_list[0].display}")
        print(f"🌐 Proxy       : {px_desc}")
    elif vpn_type != "none":
        print(f"🔄 VPN rotate  : {vpn_type} — setiap {vpn_rotate_every} akun")
    else:
        print(f"🌐 IP mode     : Direct (tanpa VPN/Proxy)")
    retry_desc = f"{max_retries - 1}x retry" if max_retries > 1 else "tanpa retry"
    print(f"🔁 Auto-retry  : {retry_desc}")
    try:
        mem = psutil.virtual_memory()
        print(f"💾 RAM         : {mem.available / (1024**2):.0f} MB tersedia / {mem.total / (1024**2):.0f} MB total")
    except Exception:
        pass
    print("═══════════════════════════════════════")
    print()

    confirm = input("Mulai? (y/n): ").strip().lower()
    if confirm != "y":
        print("Dibatalkan.")
        sys.exit(0)

    print("\n🚀 Memulai proses...\n")

    completed = 0
    success = 0
    failed = 0
    accounts_since_rotate = 0

    # Rotate VPN awal
    if vpn_type != "none":
        print("🔄 [VPN] Rotate awal...")
        rotate_vpn(vpn_type, vpn_disconnect_cmd, vpn_connect_cmd)

    # ── Process in batches ────────────────────────────────
    queue = list(range(1, total + 1))

    while queue:
        batch = queue[:threads]
        queue = queue[threads:]

        if threads == 1:
            # Sequential — simpler, no thread pool
            for tid in batch:
                pwd = generate_password()
                vcc = get_next_vcc()
                px = get_next_proxy()
                result = run_bot_with_retry(tid, pwd, vcc, headless, use_api_email,
                                            proxy=px, get_next_proxy_fn=get_next_proxy,
                                            max_retries=max_retries)
                completed += 1
                accounts_since_rotate += 1
                if result:
                    success += 1
                else:
                    failed += 1
        else:
            # Parallel threads
            futures = {}
            with ThreadPoolExecutor(max_workers=threads) as pool:
                for i, tid in enumerate(batch):
                    pwd = generate_password()
                    vcc = get_next_vcc()
                    px = get_next_proxy()
                    fut = pool.submit(run_bot_with_retry, tid, pwd, vcc, headless, use_api_email,
                                      proxy=px, get_next_proxy_fn=get_next_proxy,
                                      max_retries=max_retries)
                    futures[fut] = tid
                    # Stagger delay — beri jeda antar submit supaya
                    # browser tidak berebut resource bersamaan
                    if i < len(batch) - 1:
                        time.sleep(8)

                for fut in as_completed(futures):
                    completed += 1
                    accounts_since_rotate += 1
                    try:
                        result = fut.result()
                        if result:
                            success += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1

        print(f"\n📈 Progress: {completed}/{total} | ✅ {success} | ❌ {failed}\n")

        # VPN rotation check
        if vpn_type != "none" and accounts_since_rotate >= vpn_rotate_every and queue:
            print(f"🔄 [VPN] Sudah {accounts_since_rotate} akun — rotate IP...")
            rotate_vpn(vpn_type, vpn_disconnect_cmd, vpn_connect_cmd)
            accounts_since_rotate = 0

        # Delay between batches
        if queue:
            print("⏳ Delay 5 detik sebelum batch berikutnya...")
            time.sleep(5)

    # ── Final summary ─────────────────────────────────────
    print("\n╔══════════════════════════════════════════╗")
    print("║              📊 HASIL AKHIR               ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Total    : {total}")
    print(f"║  Berhasil : {success}")
    print(f"║  Gagal    : {failed}")
    print(f"║  Output   : {OUTPUT_FILE}")
    if CLOUD_ENABLED:
        print(f"║  Cloud    : ☁️  Google Sheets (aktif)")
    else:
        print(f"║  Cloud    : ❌ Tidak aktif")
    print("╚══════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
