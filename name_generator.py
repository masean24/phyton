"""
Random Name Generator — nama Indonesia
"""

import random

FIRST_NAMES_MALE = [
    'Adi', 'Agus', 'Ahmad', 'Andi', 'Arief', 'Bagus', 'Bambang', 'Budi',
    'Cahyo', 'Dani', 'Dedi', 'Dimas', 'Dwi', 'Eko', 'Fajar', 'Fauzi',
    'Gilang', 'Hadi', 'Hendra', 'Irfan', 'Joko', 'Kevin', 'Lutfi',
    'Muhammad', 'Naufal', 'Oscar', 'Pandu', 'Rafi', 'Rizky', 'Sigit',
    'Surya', 'Taufik', 'Umar', 'Wahyu', 'Yusuf', 'Zainal',
]

FIRST_NAMES_FEMALE = [
    'Anisa', 'Aulia', 'Bunga', 'Citra', 'Devi', 'Dewi', 'Dian', 'Eka',
    'Fitri', 'Gita', 'Indah', 'Kartika', 'Lestari', 'Maya', 'Mega',
    'Nadia', 'Nurul', 'Putri', 'Rani', 'Ratna', 'Rini', 'Sarah',
    'Sinta', 'Siti', 'Sri', 'Tika', 'Tri', 'Vina', 'Wulan', 'Yuni',
]

LAST_NAMES = [
    'Pratama', 'Wijaya', 'Kusuma', 'Santoso', 'Lestari', 'Gunawan',
    'Saputra', 'Hidayat', 'Ningsih', 'Putra', 'Permana', 'Setiawan',
    'Nugroho', 'Wibowo', 'Rahayu', 'Suryadi', 'Firmansyah', 'Ramadhan',
    'Prasetyo', 'Kurniawan', 'Susanto', 'Hartono', 'Sari', 'Purnama',
    'Aditya', 'Utama', 'Maulana', 'Hakim', 'Perdana', 'Wicaksono',
]


def generate_random_name() -> str:
    is_male = random.random() > 0.5
    first = random.choice(FIRST_NAMES_MALE if is_male else FIRST_NAMES_FEMALE)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}"
