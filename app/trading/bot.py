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

class CryptoSentinelBot:
    """
    Main trading bot class that orchestrates market analysis, signal detection,
    and trade execution.
    """

    def __init__(self):
        """Bot için gerekli modülleri başlatır."""
        print("🚀 Crypto Sentinel: HİBRİT TRADER MODU (Dynamic ROE Logic) v8.2 (Fix)...\n")
        
        # Modülleri başlat
        self.client = BinanceClient()
        self.analyzer = MarketAnalyzer()
        self.bot = TelegramBot()
        self.db_manager = DatabaseManager()
        self.streamer = StreamManager()

    def start_services(self) -> None:
        """Arka plan servislerini (WebSocket) başlatır ve veritabanı temizliği yapar."""
        print("📡 Servisler başlatılıyor...")
        
        # Start WebSocket Stream
        self.streamer.start()
        
        # Initial Database Maintenance
        self.db_manager.maintenance_clean_data(days=3)
        
        # Cüzdan Bakiyesini Getir
        balance = 0
        try:
            balance = self.db_manager.get_balance()
        except:
            balance = config.INITIAL_CAPITAL

        # Send Startup Message
        startup_msg = (
            f"🚀 SİSTEM AKTİF!\n"
            f"------------------\n"
            f"💰 Kasa: {balance:.2f} $\n"
            f"📡 Mod: Hybrid (WebSocket)\n"
            f"⚡ Kaldıraç: {config.LEVERAGE}x\n"
            f"🎯 Baz Hedef ROE: %{config.TARGET_ROE_TP*100}\n"
            f"🛑 Baz Risk ROE: %{config.TARGET_ROE_SL*100}"
        )
        try:
            self.bot.send_message(startup_msg)
        except Exception as e:
            print(f"⚠️ Telegram Başlangıç Mesajı Hatası: {e}")

    def process_coin(self, coin: str, open_trades: pd.DataFrame) -> None:
        """Tek bir coini analiz eder ve işlem fırsatlarını değerlendirir."""
        df = self.client.get_ohlcv(coin)
        
        if df is None:
            return

        # 1. Technical Analysis
        # Yeni: Multi-Timeframe Pivot Verisini Çek
        pivot_data = self.client.get_pivot_data(coin)
        
        # Pivot verisini analyzer'a gönder
        df = self.analyzer.calculate_indicators(df, pivot_data=pivot_data)
        
        _, current_score = self.analyzer.check_signals(df, coin)

        # 2. Piyasa Rejimi ve Volatilite Kontrolü
        last_row = df.iloc[-1]
        
        vol_result = self.analyzer.get_volatility_multiplier(df)        
        
        if isinstance(vol_result, tuple):
            volatility_multiplier, regime_name = vol_result
        else:
            volatility_multiplier = vol_result
            if volatility_multiplier < 1.0: regime_name = "SQUEEZE (Sıkışma)"
            elif volatility_multiplier > 1.0: regime_name = "VOLATILE (Hareketli)"
            else: regime_name = "NORMAL (Trend)"

        # 3. Piyasa Verilerini Kaydet
        df['symbol'] = coin
        df['sentinel_score'] = df.apply(lambda row: self.analyzer.calculate_sentinel_score(row), axis=1)
        self.db_manager.save_to_db(df.tail(1), 'market_data')

        last_price = last_row['close']
        
        # 4. Açık İşlem Kontrolü
        active_trade = open_trades[open_trades['symbol'] == coin] if not open_trades.empty else pd.DataFrame()

        if not active_trade.empty:
            trade_data = active_trade.iloc[0]
            print(f" 🛡️ {coin} Korunuyor... (Giriş: {trade_data['entry_price']})")
        else:
            # --- CIRCUIT BREAKER KONTROLÜ ---
            if self._check_circuit_breaker(current_score):
                print(f" ❄️ Circuit Breaker Aktif (İşlem Engellendi) - {coin}")
            else:
                self._evaluate_new_trade(coin, last_price, current_score, regime_name, volatility_multiplier)

    def _check_circuit_breaker(self, current_score: float) -> bool:
        """
        Akıllı Şalter Kontrolü:
        Günlük limitler aşıldıysa ve soğuma süresi bitmediyse TRUE döner (İşlem Engellenir).
        High Confidence (80-20) durumunda limitler esnetilir.
        """
        # 1. Güncel PnL Durumunu Çek (Son 24 Saat)
        recent_pnl = self.db_manager.get_recent_pnl(hours=24)
        
        # 2. Limitleri Belirle
        target_profit = config.DAILY_TARGET_PROFIT
        max_loss = config.DAILY_MAX_LOSS
        
        # Eğer çok güçlü bir sinyal varsa limitleri esnet
        if current_score >= 80 or current_score <= 20:
            target_profit = config.EXTENDED_TARGET_PROFIT
            max_loss = config.EXTENDED_MAX_LOSS

        # 3. Limit Kontrolü
        # Kar hedefi aşıldıysa VEYA Zarar limiti delindiyse (max_loss negatiftir, örn: -50)
        is_limit_hit = (recent_pnl >= target_profit) or (recent_pnl <= max_loss)
        
        if not is_limit_hit:
            return False # Sorun yok, işlem açılabilir
            
        # 4. Limit Aşıldıysa Soğuma Süresine Bak
        last_exit = self.db_manager.get_last_trade_exit_time()
        
        if not last_exit:
            return False # Hiç işlem yoksa devam
            
        # last_exit bir string gelebilir, datetime objesine çevir
        if isinstance(last_exit, str):
            last_exit = datetime.strptime(last_exit, "%Y-%m-%d %H:%M:%S.%f") # Format değişebilir, dikkat

        time_since_exit = datetime.now() - last_exit
        cooldown_delta = timedelta(hours=config.TRADING_COOLDOWN_HOURS)
        
        if time_since_exit < cooldown_delta:
            remaining = cooldown_delta - time_since_exit
            hours, remainder = divmod(remaining.seconds, 3600)
            mins, _ = divmod(remainder, 60)
            
            # Logu her saniye basmamak için burayı sessiz geçebiliriz veya özel bir log condition ekleriz.
            # Şimdilik process_coin içinde tek satır basıyoruz.
            return True # ENGELLE
            
        return False # Süre dolmuş, tekrar izin ver

    def _evaluate_new_trade(self, coin: str, last_price: float, current_score: float, regime_name: str, volatility_multiplier: float) -> None:
        """Puan ve rejime göre yeni işlem açılışını, pozisyon büyüklüğünü ve bakiyeyi değerlendirir."""
        # last_price'ı entry_price olarak tanımlıyoruz
        entry_price = last_price 

        # --- 0. TEKRAR İŞLEM KONTROLÜ ---
        fresh_open_trades = self.db_manager.get_open_trades()
        if not fresh_open_trades.empty and coin in fresh_open_trades['symbol'].values:
            return

        # --- 1. POZİSYON BÜYÜKLÜĞÜ (RİSK YÖNETİMİ) ---
        position_size = 0.0
        confidence = "DÜŞÜK"

        # Config'den değerleri al
        # RISK_VARS kullanılır
        high_size = config.RISK_VARS.get('HIGH', 100.0)
        med_size = config.RISK_VARS.get('MEDIUM', 50.0)
        low_size = config.RISK_VARS.get('LOW', 25.0)

        if current_score >= 80 or current_score <= 20:
            position_size = high_size
            confidence = "YÜKSEK"
        elif (current_score >= 60 and current_score < 80) or (current_score > 20 and current_score <= 40):
            position_size = med_size
            confidence = "ORTA"
        else:
            position_size = low_size
            confidence = "DÜŞÜK"


        # --- 2. BAKİYE KONTROLÜ (SANAL CÜZDAN) ---
        # Veritabanından bakiye sorgula
        try:
            current_balance = self.db_manager.get_balance()
        except:
            current_balance = 0.0

        if current_balance < position_size:
            # print(f"⚠️ Yetersiz Bakiye! ({coin} için {position_size}$ gerekiyor, Mevcut: {current_balance:.2f}$)")
            return

        # --- 3. DİNAMİK HEDEF HESAPLAMA ---
        dynamic_tp_roe = config.TARGET_ROE_TP * volatility_multiplier
        dynamic_sl_roe = config.TARGET_ROE_SL * volatility_multiplier
        
        required_move_tp = dynamic_tp_roe / config.LEVERAGE 
        required_move_sl = dynamic_sl_roe / config.LEVERAGE 

        liq_price = 0.0
        tp_price = 0.0
        sl_price = 0.0
        target_position = None
        
        # --- 4. SİNYAL YÖNÜ BELİRLEME ---
        if current_score >= 60:
            target_position = "LONG"
            liq_price = entry_price * (1 - (1 / config.LEVERAGE))
            tp_price = entry_price * (1 + required_move_tp)
            sl_price = entry_price * (1 - required_move_sl)

        elif current_score <= 40:
            target_position = "SHORT"
            liq_price = entry_price * (1 + (1 / config.LEVERAGE))
            tp_price = entry_price * (1 - required_move_tp)
            sl_price = entry_price * (1 + required_move_sl)

        # İşlem Mantığı (Transactional)
        if target_position:
            # 1. Veritabanına Yaz
            success = self.db_manager.open_trade(
                coin, target_position, entry_price, liq_price, tp_price, sl_price, position_size, timeframe=config.TIMEFRAME
            )
            
            # 2. Başarılıysa Bildirim Gönder
            if success:
                safe_regime_name = str(regime_name).replace("_", " ").replace("*", "")

                print("-" * 30)
                print(f"🌪️ REGIME: {safe_regime_name} (Çarpan: {volatility_multiplier}x)")
                print(f"💰 CÜZDAN: {current_balance:.2f}$ | RİSK: {position_size}$ ({confidence})")
                print(f"🚀 SİNYAL: {target_position} ({current_score} Puan)")
                print(f"✅ İŞLEM BAŞARIYLA AÇILDI: {coin}")
                
                icon = "🐂" if target_position == "LONG" else "🐻"
                msg = (
                    f"🚀 YENİ İŞLEM AÇILDI {icon}\n"
                    f"--------------------------------\n"
                    f"💎 Coin: {coin}\n"
                    f"⚖️ Yön: {target_position}\n"
                    f"🌪️ Rejim: {safe_regime_name}\n"
                    f"📊 Güven: {confidence} ({current_score})\n"
                    f"💰 Büyüklük: {position_size} $\n"
                    f"💵 Giriş: {entry_price:.2f} $\n"
                    f"--------------------------------\n"
                    f"🎯 Hedef (TP): {tp_price:.2f} $\n"
                    f"🛑 Stop (SL): {sl_price:.2f} $\n"
                    f"⚡ Kaldıraç: {config.LEVERAGE}x\n"
                    f"🏦 Kalan Bakiye: {current_balance - position_size:.2f} $\n"
                    f"--------------------------------"
                )
                try:
                    self.bot.send_message(msg)
                except Exception as e:
                    print(f"⚠️ Mesaj Gönderilemedi: {e}")
            else:
                pass

        else:
            print(f" 💤 {coin} İzleniyor... (Puan: {current_score})")

    def stop(self) -> None:
        """Stops all running services."""
        if hasattr(self, 'streamer') and self.streamer:
            self.streamer.keep_running = False
            if self.streamer.ws:
                self.streamer.ws.close()
        print("🛑 Bot ve servisler başarıyla durduruldu.")

    def run(self) -> None:
        """Main execution loop."""
        self.start_services()
        
        try:
            while True:
                open_trades = self.db_manager.get_open_trades()

                for coin in config.SYMBOLS:
                    self.process_coin(coin, open_trades)
                    print("-" * 30)
                    time.sleep(1) 

                print("⏳ Analiz turu bitti. 30 sn bekleme...")
                time.sleep(30) 
                
        except KeyboardInterrupt:
            print("\n🛑 Döngü kırıldı.")
        except Exception as e:
            print(f"⚠️ Kritik Hata: {e}")
            time.sleep(5)
        finally:
            self.stop()