"""
VCC Generator Module
Generate valid credit card numbers using Luhn algorithm from a BIN
Supports two modes: generate from BIN, or parse from a pre-made list
"""

import random
import secrets
from dataclasses import dataclass
from typing import Optional


# ─── Luhn ────────────────────────────────────────────────────────────────────

def luhn_check(num: str) -> bool:
    total = 0
    alternate = False
    for i in range(len(num) - 1, -1, -1):
        n = int(num[i])
        if alternate:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alternate = not alternate
    return total % 10 == 0


# ─── Card network detection ──────────────────────────────────────────────────

def detect_network(bin_str: str) -> str:
    n = int(bin_str[:2])
    if bin_str[0] == '4':
        return 'Visa'
    if (51 <= n <= 55) or (2221 <= int(bin_str[:4]) <= 2720):
        return 'Mastercard'
    if n in (34, 37):
        return 'Amex'
    if bin_str.startswith('6011') or bin_str.startswith('65') or (64 <= n <= 65):
        return 'Discover'
    if bin_str.startswith('62') or bin_str.startswith('81'):
        return 'UnionPay'
    return 'Unknown'


# ─── Card number generator ───────────────────────────────────────────────────

def generate_card_number(bin_str: str) -> str:
    network = detect_network(bin_str)
    total_len = 15 if network == 'Amex' else 16
    pad_len = total_len - 1

    card = bin_str
    while len(card) < pad_len:
        card += str(secrets.randbelow(10))

    # Calculate Luhn check digit
    total = 0
    alternate = True
    for i in range(len(card) - 1, -1, -1):
        n = int(card[i])
        if alternate:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alternate = not alternate
    check_digit = (10 - (total % 10)) % 10
    card += str(check_digit)
    return card


# ─── CVC generator ───────────────────────────────────────────────────────────

def generate_cvc(network: str) -> str:
    length = 4 if network == 'Amex' else 3
    min_val = 10 ** (length - 1)
    max_val = (10 ** length) - 1
    return str(secrets.randbelow(max_val - min_val + 1) + min_val)


# ─── Formatter ───────────────────────────────────────────────────────────────

def format_card_number(card_number: str) -> str:
    if len(card_number) == 15:
        return f"{card_number[:4]} {card_number[4:10]} {card_number[10:]}"
    return ' '.join(card_number[i:i+4] for i in range(0, len(card_number), 4))


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class VCCConfig:
    bin: str
    exp_month: str
    exp_year: str


@dataclass
class GeneratedVCC:
    number: str
    formatted: str
    exp_month: str
    exp_year: str
    expiry: str
    cvc: str
    network: str
    source: str  # 'generated' or 'list'


# ─── Public API ──────────────────────────────────────────────────────────────

def generate_vcc(config: VCCConfig) -> GeneratedVCC:
    network = detect_network(config.bin)
    number = generate_card_number(config.bin)
    return GeneratedVCC(
        number=number,
        formatted=format_card_number(number),
        exp_month=config.exp_month,
        exp_year=config.exp_year,
        expiry=f"{config.exp_month}/{config.exp_year}",
        cvc=generate_cvc(network),
        network=network,
        source='generated',
    )


def parse_vcc_line(line: str) -> Optional[GeneratedVCC]:
    """Parse a single line from vcc-list.txt. Format: NUMBER|MM/YY|CVC"""
    trimmed = line.strip()
    if not trimmed or trimmed.startswith('#'):
        return None

    parts = trimmed.split('|')
    if len(parts) < 3:
        return None

    number = parts[0].replace(' ', '')
    expiry = parts[1].strip()
    cvc = parts[2].strip()

    import re
    if not re.match(r'^\d{15,16}$', number):
        return None
    if not luhn_check(number):
        return None

    exp_match = re.match(r'^(\d{2})/(\d{2,4})$', expiry)
    if not exp_match:
        return None

    exp_month = exp_match.group(1)
    exp_year = exp_match.group(2)
    if len(exp_year) == 4:
        exp_year = exp_year[2:]

    if not cvc or not re.match(r'^\d{3,4}$', cvc):
        return None

    network = detect_network(number)
    return GeneratedVCC(
        number=number,
        formatted=format_card_number(number),
        exp_month=exp_month,
        exp_year=exp_year,
        expiry=f"{exp_month}/{exp_year}",
        cvc=cvc,
        network=network,
        source='list',
    )


def validate_bin(bin_str: str) -> bool:
    import re
    return bool(re.match(r'^\d{6,8}$', bin_str))
