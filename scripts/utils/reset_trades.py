from app.core.database import DatabaseManager
from sqlalchemy import text

def reset_open_trades():
    db = DatabaseManager()
    print("🧹 'OPEN' statüsündeki işlemler siliniyor/kapatılıyor (TEST İÇİN)...")
    
    # İstersen silmek yerine statüyü CLOSED yapabilirsin
    # query = text("UPDATE trade_history SET status = 'CLOSED_TEST' WHERE status = 'OPEN'")
    
    # Hepsini silip temiz başlangıç yapalım
    query = text("DELETE FROM trade_history WHERE status = 'OPEN'")
    
    try:
        with db.engine.connect() as conn:
            result = conn.execute(query)
            conn.commit()
            print(f"✅ {result.rowcount} adet açık işlem silindi.")
    except Exception as e:
        print(f"❌ Hata: {e}")

if __name__ == "__main__":
    reset_open_trades()
