# main.py
from app.trading.bot import CryptoSentinelBot

def main():
    """
    Application Entry Point.
    Initializes and runs the CryptoSentinelBot.
    """
    try:
        bot = CryptoSentinelBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n� Çıkış yapılıyor...")
    except Exception as e:
        print(f"❌ Kritik Başlatma Hatası: {e}")

if __name__ == "__main__":
    main()

