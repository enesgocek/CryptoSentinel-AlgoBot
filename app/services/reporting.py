import schedule
import time
import pandas as pd
from datetime import datetime, timedelta
from app.core import config
from app.core.database import DatabaseManager
from app.services.telegram_bot import TelegramBot

class DailyReporter:
    def __init__(self):
        self.db = DatabaseManager()
        self.bot = TelegramBot()

    def generate_daily_report(self):
        """Günlük işlem raporunu oluşturur ve Telegram'dan gönderir."""
        print("📊 Günlük Rapor Hazırlanıyor...")
        
        # 1. Verileri Çek (Son 24 Saat)
        df = self.db.get_daily_trades(hours=24)
        
        if df.empty:
            msg = "📅 **Günlük Kripto Raporu**\n-------------------\n💤 Son 24 saatte kapanan işlem yok.\n*Sistem taramaya devam ediyor...*"
            self.bot.send_message(msg)
            return

        # 2. Metrikleri Hesapla
        total_trades = len(df)
        wins = len(df[df['pnl'] > 0])
        losses = len(df[df['pnl'] <= 0])
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        # PnL Hesabı: (PnL% / 100) * (Exit Size + Profit taken earlier? No, simpler: Realized PnL from wallet updates logic)
        # Veritabanında her işlem için "ne kadar kazandırdı" diye bir sütun yok, dinamik hesaplamalıyız.
        # Logic: 
        #   Realized PnL = (Exit Price - Entry Price) * Usage Size * Leverage ... karmaşık.
        #   Basitleştirilmiş: (PnL% / 100) * Initial Size (Yaklaşık).
        #   Daha Doğrusu: (PnL% / 100) * exit_size (Eğer partial ise).
        #   Fakat en temizi: `wallet` tablosundaki değişimleri toplamak olurdu ama o tablo karışık.
        #   Biz yine de yaklaşık hesabı 'exit_size' ve 'current_size' üzerinden yapamayız çünkü onlar anlık.
        #   En iyisi: `(pnl / 100) * position_size` (Initial). Bu toplam potansiyeli gösterir.
        #   Fakat bu partial çıkışları abartır.
        #   
        #   ÇÖZÜM: `pnl` sütunu işlem kapandığında gerçekleşen son PnL yüzdesidir.
        #   Tam doğru tutar takibi için `realized_pnl` sütunu eklemek gerekirdi.
        #   Şimdilik "Yaklaşık Net Kar" olarak `(Sum of PnL) / 100 * Average Size` gibi bir şey yerine
        #   Kullanıcıya PnL puanı vermek daha dürüst olabilir.
        #   
        #   Veya: (pnl * position_size / 100) formülünü kullanalım, bu "eğer hiç satış yapmasaydık ne olurdu"yu gösterir.
        #   Moonbag için: `(pnl * exit_size / 100)` mantıklı.
        
        # Basit PnL Sum (Dolar bazlı değil, Puan bazlı)
        total_pnl_score = df['pnl'].sum()
        
        # Moonbag Bonusu
        moonbag_trades = df[ (df['status'] == 'MOONBAG_CLOSED') | (df['is_moonbag_filled'] == True) ]
        moonbag_count = len(moonbag_trades)
        
        # 3. Mesajı Formatla
        # Emoji Seçimi
        pnl_emoji = "💰" if total_pnl_score > 0 else "🔻"
        
        msg = (
            f"📅 **GÜNLÜK KRİPTO RAPORU**\n"
            f"-------------------------\n"
            f"{pnl_emoji} **Net PnL Skoru:** %{total_pnl_score:.2f}\n"
            f"📊 **Win/Loss:** {wins}W - {losses}L (WR: %{win_rate:.0f})\n"
            f"🌕 **Moonbag Bonusu:** {moonbag_count} adet işlemden ekstra kazanç.\n"
            f"-------------------------\n"
            f"🤖 *Sistem Aktif & Taramada...*"
        )
        
        # 4. Gönder
        self.bot.send_message(msg)
        print("✅ Günlük Rapor Gönderildi.")

    def run_scheduler(self):
        """Zamanlayıcıyı başlatır (Ana döngü içinde çağrılmalı)."""
        # Her sabah 08:00 UTC (TSİ 11:00)
        schedule.every().day.at("08:00").do(self.generate_daily_report)
        print("⏰ Rapor Zamanlayıcısı Kuruldu (08:00 UTC)")
