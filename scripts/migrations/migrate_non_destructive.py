from sqlalchemy import create_engine, text
from app.core import config

def migrate_non_destructive():
    print("🔌 Veritabanına bağlanılıyor...")
    engine = create_engine(config.DB_CONNECTION_STRING)
    
    with engine.connect() as conn:
        print("🛠️ Şema Güncelleniyor: Non-Destructive Tracking (Veri Kaybı Önleme)")
        
        # 1. current_size (Aktif Büyüklük)
        try:
            conn.execute(text("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS current_size REAL;"))
            print("✅ 'current_size' sütunu eklendi.")
        except Exception as e:
            print(f"⚠️ current_size eklenirken hata veya zaten var: {e}")
            
        # 2. exit_size (Çıkış Büyüklüğü)
        try:
            conn.execute(text("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS exit_size REAL;"))
            print("✅ 'exit_size' sütunu eklendi.")
        except Exception as e:
            print(f"⚠️ exit_size eklenirken hata veya zaten var: {e}")

        # 3. VERİ KURTARMA (Backfill)
        # Mevcut verilerde current_size boş ise, position_size değerini kopyala.
        # Bu, eski işlemlerin bozulmamasını sağlar.
        try:
            conn.execute(text("UPDATE trade_history SET current_size = position_size WHERE current_size IS NULL;"))
            print("🔄 Eski veriler kurtarıldı (Backfill: position_size -> current_size).")
        except Exception as e:
            print(f"❌ Backfill hatası: {e}")

        conn.commit()
    
    print("🎉 Migrasyon Başarıyla Tamamlandı! Veritabanı artık 'Güvenli Mod'da.")

if __name__ == "__main__":
    migrate_non_destructive()
