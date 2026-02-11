import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- MEVCUT AYARLAR ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
TIMEFRAME = '1h'
LIMIT = 1000

# --- YENİ BİNANCE TRADER AYARLARI (ROE MANTIĞI) ---
LEVERAGE = 25         # Kaldıraç Oranı

# Fiyat artışı yerine, ana para getirisini (ROE) hedefler.
# Örn: 10x kaldıraçta %50 ROE için fiyatın %5 artması yeterlidir.

TARGET_ROE_TP = 0.50 # %50 Kar Hedefi (ROE)
TARGET_ROE_SL = 0.30 # %30 Zarar Kes (ROE)

# --- CIRCUIT BREAKER (AKILLI ŞALTER) ---
# Günlük Kar/Zarar Hedefleri ve Soğuma Süresi
DAILY_TARGET_PROFIT = 200.0   # Günlük 100$ Kar Hedefi (Dur)
DAILY_MAX_LOSS = -100.0        # Günlük 50$ Zarar Limiti (Dur)
TRADING_COOLDOWN_HOURS = 8    # Limitler aşılırsa 8 saat bekle

# Yüksek Güvenli İşlemler İçin Esnek Limitler
EXTENDED_TARGET_PROFIT = 400.0 # Güçlü sinyalde hedefi 200$'a çıkar
EXTENDED_MAX_LOSS = -175.0     # Güçlü sinyalde zarara 125$'a kadar tahammül et

# === SANAL CÜZDAN & RİSK YÖNETİMİ ===
INITIAL_CAPITAL = 1000.0 # Başlangıç Bakiyesi (USDT)

# Güven Skoruna Göre Risk Kademeleri
# Skor >= 80 veya <= 20 -> Yüksek Güven
# Skor 60-79 veya 21-40 -> Orta Güven
# Skor 40-59 -> Düşük Güven
RISK_VARS = {
    'HIGH': 100.0,   # Yüksek: 100$
    'MEDIUM': 50.0,  # Orta: 50$
    'LOW': 25.0      # Düşük: 25$
}

# --- PİYASA REJİMİ & VOLATİLİTE AYARLARI ---
BB_LENGTH = 20        # Bollinger Bant Periyodu
BB_STD = 2.0          # Standart Sapma
ADX_LENGTH = 14       # Trend Gücü Periyodu
BBW_LOOKBACK = 100    # Geçmiş Veri Bakış Aralığı


# Veritabanı Bağlantı Linkin
# DB_CONNECTION_STRING = "..."

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not DB_CONNECTION_STRING:
    print("WARNING: One or more environment variables are missing. Please check your .env file.")
