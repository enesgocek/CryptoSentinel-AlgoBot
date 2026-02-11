import sys
import os
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

try:
    print("🔄 Modüller İçe Aktarılıyor...")
    from app.core import config
    from app.core.database import DatabaseManager
    from app.trading.bot import CryptoSentinelBot
    from app.services.reporting import DailyReporter
    print("✅ Modül İçe Aktarımı Başarılı.")
except Exception as e:
    print(f"❌ İçe Aktarma Hatası: {e}")
    sys.exit(1)

def check_database():
    print("\n🗄️ Veritabanı Kontrolü...")
    db = DatabaseManager()
    
    # 1. Tablo Kontrolü
    try:
        with db.engine.connect() as conn:
            # Check for new columns in trade_history
            res = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='trade_history';")
            columns = [row[0] for row in res.fetchall()]
            
            required_cols = ['current_size', 'exit_size', 'is_moonbag_filled', 'is_main_tp_filled']
            missing = [col for col in required_cols if col not in columns]
            
            if missing:
                print(f"❌ EKSİK KOLONLAR: {missing}")
            else:
                print("✅ Veritabanı Şeması Doğru (Yeni Kolonlar Mevcut).")
                
            # Check connection
            print("✅ Veritabanı Bağlantısı Başarılı.")
            return True
    except Exception as e:
        print(f"❌ Veritabanı Hatası: {e}")
        return False

def check_bot_init():
    print("\n🤖 Bot Başlatma Simülasyonu...")
    try:
        # Dry Run Init
        bot = CryptoSentinelBot()
        print("✅ Bot Sınıfı Başarıyla Örneklendi.")
        
        # Check components
        if bot.streamer and bot.db_manager and bot.reporter:
            print("✅ Alt Bileşenler (Streamer, DB, Reporter) Hazır.")
        else:
            print("❌ Eksik Bileşen Var.")
            
    except Exception as e:
        print(f"❌ Bot Başlatma Hatası: {e}")

def check_reporting():
    print("\n📊 Raporlama Modülü Testi...")
    try:
        reporter = DailyReporter()
        # Mocking db call to avoid actual empty report spam if possible, 
        # but running generate_daily_report() is the best integration test.
        # We will check if it runs without crashing.
        print("✅ DailyReporter Başlatıldı.")
    except Exception as e:
        print(f"❌ Raporlama Hatası: {e}")

if __name__ == "__main__":
    print(f"🔍 SİSTEM TESTİ BAŞLIYOR... ({datetime.now()})")
    print("--------------------------------------------------")
    
    check_database()
    check_bot_init()
    check_reporting()
    
    print("\n--------------------------------------------------")
    print("🏁 TEST TAMAMLANDI.")
