import sqlite3
import os

# Veritabanı dosyasının yolu
DB_PATH = 'neon.db'  # Eger senin dosya adin farkliysa burayi duzelt (bazen crypto_sentinel.db olabilir)

def clean_database():
    if not os.path.exists(DB_PATH):
        print(f"❌ HATA: Veritabanı dosyası bulunamadı: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🧹 Temizlik Başlıyor...")

    # 1. SAHTE TEST İŞLEMLERİNİ SİL (TEST_ ile başlayanlar)
    cursor.execute("SELECT count(*) FROM trades WHERE symbol LIKE 'TEST_%'")
    fake_count = cursor.fetchone()[0]
    
    if fake_count > 0:
        cursor.execute("DELETE FROM trades WHERE symbol LIKE 'TEST_%'")
        print(f"✅ {fake_count} adet sahte 'TEST' işlemi silindi.")
    else:
        print("✅ Silinecek sahte işlem bulunamadı.")

    # 2. SAHTE BAKİYE GEÇMİŞİNİ TEMİZLE (Opsiyonel ama temiz olsun)
    # Son eklenen ve bakiyesi anormal yüksek olan satırları manuel kontrol etmek zor
    # O yüzden en sonuncuyu gerçek bakiye ile güncelleyeceğiz.

    # 3. GERÇEK BAKİYEYİ EŞİTLE
    print("\n------------------------------------------------")
    print("⚠️ DİKKAT: Botun şu anki veritabanı bakiyesi yanlış görünüyor.")
    real_balance = float(input("💰 Lütfen Binance USDT Bakiyeni Yaz (Örn: 1140.5): "))
    
    # Balance history tablosuna gerçek bakiyeyi ekle
    cursor.execute("INSERT INTO balance_history (timestamp, balance) VALUES (CURRENT_TIMESTAMP, ?)", (real_balance,))
    
    print(f"✅ Veritabanı bakiyesi {real_balance}$ olarak güncellendi.")
    
    conn.commit()
    conn.close()
    print("\n🎉 Temizlik Tamamlandı! Botu şimdi başlatabilirsin.")

if __name__ == "__main__":
    clean_database()