import time
import pandas as pd

from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

from app.core import config
from app.core.database import DatabaseManager
from app.services.binance_client import BinanceClient
from app.services.telegram_bot import TelegramBot
from app.analysis.analyzer import MarketAnalyzer
from app.trading.stream_manager import StreamManager
from app.services.reporting import DailyReporter
import schedule

class CryptoSentinelBot:
    # ... (existing code)

    def __init__(self):
        # ... (existing code)
        self.streamer = StreamManager()
        self.reporter = DailyReporter() # Raporcu Başlatıldı

    # ... (start_services method unchanged)

    def run(self) -> None:
        """Main execution loop."""
        self.start_services()
        
        # Zamanlayıcıyı Kur
        self.reporter.run_scheduler()
        
        try:
            while True:
                # 1. Zamanlanmış Görevleri Kontrol Et
                schedule.run_pending()
                
                open_trades = self.db_manager.get_open_trades()

                for coin in config.SYMBOLS:
                    self.process_coin(coin, open_trades)
                    print("-" * 30)
                    time.sleep(1) 

                print("⏳ Analiz turu bitti. 10 sn bekleme...")
                time.sleep(10) 
                
        except KeyboardInterrupt:
            print("\n🛑 Döngü kırıldı.")
        except Exception as e:
            print(f"⚠️ Kritik Hata: {e}")
            time.sleep(5)
        finally:
            self.stop()