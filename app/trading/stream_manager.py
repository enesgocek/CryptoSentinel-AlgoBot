# stream_manager.py
import websocket
import json
import threading
import time
import pandas as pd
from app.core import config
from app.core.database import DatabaseManager
from app.services.telegram_bot import TelegramBot



class StreamManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.bot = TelegramBot()
        self.ws = None
        self.keep_running = True
        
        streams = [f"{s.replace('/', '').lower()}@miniTicker" for s in config.SYMBOLS]
        stream_string = "/".join(streams)
        self.socket_url = f"wss://stream.binance.com:9443/ws/{stream_string}"
        
        print(f"🔌 WebSocket Hazırlanıyor: {stream_string}")

    def on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
            symbol_raw = data['s']
            current_price = float(data['c'])
            
            symbol = next((s for s in config.SYMBOLS if s.replace('/', '') == symbol_raw), None)
            
            if not symbol: return
            
            # MOONBAG DESTEĞİ: Hem OPEN hem MOONBAG olanları izle
            monitored_trades = self.db.get_monitored_trades()
            if monitored_trades.empty: return

            trade = monitored_trades[monitored_trades['symbol'] == symbol]
            if not trade.empty:
                self.check_trade_conditions(trade.iloc[0], current_price)

        except Exception as e:
            print(f"⚠️ Stream Hatası: {e}")

    def check_trade_conditions(self, trade: pd.Series, current_price: float) -> None:
        trade_id = trade['id']
        entry_price = float(trade['entry_price'])
        position = trade['position']
        liq_price = float(trade['liquidation_price'])
        is_tp1_filled = trade.get('is_tp1_filled', False) # Eski kayıtlarda olmayabilir
        
        # Kaldıraç bilgisini al
        leverage = int(trade.get('leverage', config.LEVERAGE))

        # --- BİNANCE ROE HESAPLAMASI (Gerçek PNL) ---
        # Formül: (Fiyat Farkı %) * Kaldıraç = ROE
        
        if position == 'LONG':
            price_change_percent = (current_price - entry_price) / entry_price
        else: # SHORT
            price_change_percent = (entry_price - current_price) / entry_price
            
        # ROE Oranı (Örn: 0.50)
        current_roe = price_change_percent * leverage 
 

        # MESAJ ŞABLONU
        msg_template = (
            "{title}\n"
            "--------------------------------\n"
            "💎 Coin: {symbol}\n"
            "🚪 Çıkış Fiyatı: {exit_price:.2f} $\n"
            "📊 PNL (ROE): {pnl_sign}%{pnl:.2f}\n"
            "--------------------------------"
        )

        # --- CÜZDAN & PNL HESAPLAMASI ---
        # NON-DESTRUCTIVE: 'current_size' kullanılır. Yoksa 'position_size' (Initial) fallback.
        current_size = float(trade.get('current_size', trade.get('position_size', 0)))
        
        realized_pnl = 0.0
        if current_size > 0:
            realized_pnl = current_size * current_roe

        # 1. LİKİDASYON KONTROLÜ
        is_liquidated = (position == 'LONG' and current_price <= liq_price) or \
                        (position == 'SHORT' and current_price >= liq_price)

        if is_liquidated:
            print(f"💀 LİKİDASYON: {trade['symbol']}")
            
            # Likidasyon durumunda parayı kaybet (Aktif büyüklük kadar)
            loss_amount = -current_size 
            new_balance = self.db.update_balance(loss_amount)
            
            # exit_size = 0 (Her şey gitti)
            self.db.close_trade(trade_id, current_price, -100.0, 'LIQUIDATED', "Liq Fiyatına Değdi", exit_size=0)
            
            msg = msg_template.format(
                title="💀 POZİSYON LİKİT OLDU (REKT) 💀",
                symbol=trade['symbol'],
                exit_price=current_price,
                pnl_sign="-",
                pnl=100.00
            ) + f"\n💸 Zarar: {loss_amount:.2f} $\n🏦 Yeni Bakiye: {new_balance:.2f} $"
            self.bot.send_message(msg)
            return

        # 1.5 SMART SCALING OUT (TP1 & PIVOT TP - KADEMELİ KAR AL)
        # Sadece BÜYÜK ve ORTA işlemler için (Config'den dinamik alınır)
        
        threshold_high = config.RISK_VARS.get('HIGH', 100)
        threshold_medium = config.RISK_VARS.get('MEDIUM', 50)
        
        # Orjinal büyüklüğü tahmin et
        # Orjinal büyüklüğü tahmin et (ARTIK GEREK YOK - position_size zaten Initial)
        initial_size = float(trade.get('position_size', 0))
        
        is_high_risk = initial_size >= threshold_high
        is_medium_risk = threshold_medium <= initial_size < threshold_high
        
        if is_high_risk or is_medium_risk:
            
            # A. TP1 KONTROLÜ (Hedef ROE'nin Yarısı -> %25 Kar)
            # Volatiliteye göre ayarlanan gerçek hedefi (TP Price) baz alıyoruz.
            tp_price_db = float(trade.get('tp_price', 0))
            implied_target_roe = config.TARGET_ROE_TP # Fallback
            
            if tp_price_db > 0:
                try:
                    if position == 'LONG':
                        implied_target_roe = ((tp_price_db - entry_price) / entry_price) * leverage
                    else:
                        implied_target_roe = ((entry_price - tp_price_db) / entry_price) * leverage
                except: pass

            tp1_trigger_roe = implied_target_roe / 2
            
            should_take_tp1 = False
            if not is_tp1_filled and current_roe >= tp1_trigger_roe:
                should_take_tp1 = True
                
            # B. PIVOT TP KONTROLÜ (Pivot Seviyesi + Min %15 Kar)
            pivot_level_hit = False
            is_pivot_filled = trade.get('is_pivot_tp_filled', False)
            
            if not is_pivot_filled:
                pivots = self.db.get_latest_pivots(trade['symbol'])
                if pivots and current_roe > 0.15: 
                    # STRICT COMPARISON (No more demo logic)
                    if position == 'LONG':
                        # Fiyat R1, R2 veya R3'e değdi mi?
                        if (current_price >= pivots['R1']) or (current_price >= pivots['R2']) or (current_price >= pivots['R3']):
                            pivot_level_hit = True
                    elif position == 'SHORT':
                        # Fiyat S1, S2 veya S3'e değdi mi?
                        if (current_price <= pivots['S1']) or (current_price <= pivots['S2']) or (current_price <= pivots['S3']):
                            pivot_level_hit = True

            # --- EYLEM ZAMANI ---
            
            # Senaryo 1: TP1 Tetiklendi
            if should_take_tp1:
                # Kural:
                # High Risk: TP1 orjinalin %50'sini kapatır.
                # Medium Risk: TP1 pozisyonun %80'ini kapatır (Güvenli çıkış).
                
                close_ratio_current = 0.50
                
                if is_high_risk:
                     # Eğer Pivot daha önce alındıysa şu anki'nin değil, INITIAL'ın oranını kullanmak daha doğru
                     # Ama basitlik için current üzerinden gidelim.
                     if is_pivot_filled: close_ratio_current = 0.666 # Bu logic karmaşıklaşabilir, basitleştirelim:
                     else: close_ratio_current = 0.50
                elif is_medium_risk:
                     close_ratio_current = 0.80 # %80'ini sat, %20 içeride kalsın
                
                closed_amount = current_size * close_ratio_current
                realized_pnl_tp1 = closed_amount * current_roe
                new_balance = self.db.update_balance(realized_pnl_tp1)
                
                # Stop Güncelle (Breakeven)
                new_sl_price = entry_price * 1.001 if position == 'LONG' else entry_price * 0.999
                remaining_size = current_size - closed_amount
                
                if remaining_size < 1: # Çok az kaldıysa veya bittiyse kapat
                     self.db.close_trade(trade_id, current_price, current_roe*100, 'CLOSED', "TP1 + Pivot Tümü (Macro TP)", exit_size=0)
                else:
                     self.db.update_trade_after_tp1(trade_id, remaining_size, new_sl_price)
                
                print(f"TP1 ALINDI: {trade['symbol']} (Miktar: {closed_amount:.2f}$)")
                
                
                # Mesaj
                runner_pct = 20 if is_medium_risk else 50
                info_msg = f"🛡️ Medium Risk TP1: %80 Kar Cepte, %20 Runner." if is_medium_risk else f"🚀 High Risk TP1: %50 Kar Cepte, %50 Runner."
                
                msg = msg_template.format(
                    title="💰 TP1 ALINDI (ROE %25) 🛡️",
                    symbol=trade['symbol'],
                    exit_price=current_price,
                    pnl_sign="+",
                    pnl=current_roe * 100
                ) + f"\n💵 Kar: {realized_pnl_tp1:.2f} $\n📉 Kalan: {remaining_size:.2f} $\nℹ️ {info_msg}\n🎯 Sıradaki Hedef: {tp_price_db:.2f}"
                self.bot.send_message(msg)
                return

            # 3. PIVOT CHECK (Kademeli Kar Alım) - Sadece ROE > 15 ise
            # YENİ STRATEJİ: Medium Risk için %40 Kapat, Stop -> Entry
            
            # Use .get() to avoid KeyError if column is missing
            is_pivot_tp_filled = trade.get('is_pivot_tp_filled', False) 
            # Boolean conversion for safety
            if is_pivot_tp_filled in [1, '1', True, 'true', 'True']: is_pivot_tp_filled = True
            else: is_pivot_tp_filled = False

            if not is_pivot_tp_filled and pivot_level_hit:
                # Pivot trigger is now calculated above and stored in pivot_level_hit
                
                if True: # Logic flow continuation
                    # MEDIUM RISK STRATEJİSİ: %40 KAPAT, STOP -> ENTRY
                    if is_medium_risk:
                        close_ratio = 0.40 # %40
                        profit_size = current_size * close_ratio
                        remaining_size = current_size - profit_size
                        
                        realized_pnl_pivot = profit_size * current_roe
                        new_balance = self.db.update_balance(realized_pnl_pivot)
                        
                        # DB'yi Güncelle (Size küçüldü, SL -> Entry)
                        entry_price = trade['entry_price']
                        self.db.update_trade_after_pivot(trade_id, new_size=remaining_size, new_sl_price=entry_price)
                        
                        print(f"🛡️ PIVOT TP (Medium Risk): {trade['symbol']} (Kar: {realized_pnl_pivot:.2f}$, Kalan: {remaining_size}$)")
                        
                        msg = msg_template.format(
                            title="🛡️ PIVOT KAR ALIMI (Medium Risk)",
                            symbol=trade['symbol'],
                            exit_price=current_price,
                            pnl_sign="+",
                            pnl=current_roe * 100
                        ) + f"\nKV Karı: +{realized_pnl_pivot:.2f} $\n📉 Büyüklük: %40 Kapatıldı\n🛑 Stop Loss: Giriş (Breakeven)"
                        self.bot.send_message(msg)
                        return # Başka kontrole gerek yok
                    
                    # HIGH RISK & LOW RISK İÇİN PIVOT DAVRANIŞI (İsteğe bağlı, şimdilik pas geçiyoruz veya eski mantık)
                    # İsterseniz buraya High Risk için de pivot ekleyebilirsiniz.
                    # Şimdilik user sadece Medium Risk dedi.
            
        # 2. KAR AL (TP) VE STOP (SL) KONTROLÜ
        tp_price = float(trade.get('tp_price', 0))
        sl_price = float(trade.get('sl_price', 0))
        
        if tp_price == 0 or sl_price == 0: return

        is_take_profit = False
        is_stop_loss = False
        
        if position == 'LONG':
            if current_price >= tp_price: is_take_profit = True
            elif current_price <= sl_price: is_stop_loss = True
        elif position == 'SHORT':
            if current_price <= tp_price: is_take_profit = True
            elif current_price >= sl_price: is_stop_loss = True

        # --- İŞLEM KAPATMA EYLEMLERİ ---

        if is_take_profit:
            # --- MOONBAG LOGIC (Sadece High Risk İçin) ---
            # Eğer işlem zaten MOONBAG modundaysa, bu ikinci TP (200%) demektir -> Kapat.
            if trade.get('status') == 'MOONBAG':
                 print(f"🌕 MOONBAG HEDEFİ VURULDU! (200% ROE) - {trade['symbol']}")
                 new_balance = self.db.update_balance(current_size * current_roe)
                 # Exit Size = Moonbag'in kendisi
                 self.db.close_trade(trade_id, current_price, current_roe*100, 'MOONBAG_CLOSED', "MOONBAG 200% TP", is_moonbag=True, exit_size=current_size)
                 
                 msg = msg_template.format(
                    title="🌕 MOONBAG HEDEFİ (200%) 🚀",
                    symbol=trade['symbol'],
                    exit_price=current_price,
                    pnl_sign="+",
                    pnl=current_roe * 100
                 ) + f"\n🚀 Kar: +{position_size * current_roe:.2f} $\n🏦 Yeni Bakiye: {new_balance:.2f} $"
                 self.bot.send_message(msg)
                 return

            # Eğer işlem OPEN modundaysa...
            trade_status = trade.get('status', 'OPEN')
            
            # HIGH RISK -> MOONBAG
            if trade_status == 'OPEN' and is_high_risk:
                # 🌕 MOONBAG ACTIVATION
                # ... (High Risk Logic kept same) ...
                
                # Hedef: 10$ Bırak, Gerisini Sat.
                moonbag_size = 10.0
                profit_taken_size = current_size - moonbag_size
                
                # Kar Hesapla
                realized_pnl_main = profit_taken_size * current_roe
                
                # Cüzdanı Güncelle
                new_balance = self.db.update_balance(realized_pnl_main)
                
                # Trade'i Moonbag'e Çevir (Bakiyeyi güncelle, stopu girişe çek)
                # TP: Entry * (1 + 2.00 / Leverage) -> 200% ROE
                new_tp_price = trade['entry_price'] * (1 + (2.0 if trade['position'] == 'LONG' else -2.0) / trade['leverage'])
                new_sl_price = trade['entry_price'] # Breakeven
                
                self.db.set_trade_to_moonbag(trade_id, moonbag_size, new_tp_price, new_sl_price)
                
                print(f"🌕 MOONBAG AKTİF: {trade['symbol']} (Kar: {realized_pnl_main:.2f}$, Runner: 10$)")
                
                msg = msg_template.format(
                    title="🌕 MOONBAG AKTİF EDİLDİ 🚀",
                    symbol=trade['symbol'],
                    exit_price=current_price,
                    pnl_sign="+",
                    pnl=current_roe * 100
                ) + f"\n🚀 Ana Kar Alındı: +{realized_pnl:.2f} $\n👻 Moonbag (Ghost Runner): {moonbag_size}$ Bırakıldı\n🎯 Yeni Hedef: 200% ROE ({new_tp_price:.2f})"
                self.bot.send_message(msg)
                return

            # MEDIUM / LOW RISK -> TAM KAPANIŞ
            else:
                # NORMAL KAPANIŞ (Medium/Low Risk)
                title_msg = "✅ KAR ALINDI (MAIN TP) 🎯" 
                
                print(f"⚡ KAR ALINDI: {trade['symbol']} (Fiyat: {current_price}, Kar: {realized_pnl:.2f}$)")
                
                # Main TP Flag'ini Set Et (Db update)
                new_balance = self.db.update_balance(realized_pnl)
                # Tam kapanışta exit_size = current_size (hepsi satıldı)
                self.db.close_trade(trade_id, current_price, current_roe*100, 'CLOSED', "Main TP Hedefi", is_main_tp=True, exit_size=current_size)
                
                msg = msg_template.format(
                    title=title_msg,
                    symbol=trade['symbol'],
                    exit_price=current_price,
                    pnl_sign="+",
                    pnl=current_roe * 100
                ) + f"\n🚀 Toplam Kar: +{realized_pnl:.2f} $\n🏦 Yeni Bakiye: {new_balance:.2f} $"
                
                if is_medium_risk:
                     msg += "\n🛡️ Medium Risk: Tam Kapanış."
                     
                self.bot.send_message(msg)
                return

        if is_stop_loss:
            new_balance = self.db.update_balance(realized_pnl)
            
            print(f"⚡ STOP OLDU: {trade['symbol']} (Fiyat: {current_price}, Zarar: {realized_pnl:.2f}$)")
            
            # Stop olduğunda exit_size = current_size (hepsi satıldı)
            final_status = 'MOONBAG_CLOSED' if trade.get('status') == 'MOONBAG' else 'CLOSED'
            self.db.close_trade(trade_id, current_price, current_roe*100, final_status, "SL Hedefi (Fiyat)", exit_size=current_size)

            msg = msg_template.format(
                title="⚠️ STOP OLDU (STOP LOSS) 🛑",
                symbol=trade['symbol'],
                exit_price=current_price,
                pnl_sign="" if current_roe < 0 else "+",
                pnl=current_roe * 100
            ) + f"\n🛡️ PnL: {realized_pnl:.2f} $\n🏦 Yeni Bakiye: {new_balance:.2f} $"
            self.bot.send_message(msg)
            return



    def on_error(self, ws, error): print(f"⚠️ WebSocket Hatası: {error}")
    def on_close(self, ws, close_status_code, close_msg): print("🔌 WebSocket Koptu.")
    def on_open(self, ws): print("✅ Canlı Fiyat Akışı Bağlandı.")

    def start(self):
        def run():
            while self.keep_running:
                try:
                    self.ws = websocket.WebSocketApp(self.socket_url,
                                                     on_open=self.on_open,
                                                     on_message=self.on_message,
                                                     on_error=self.on_error,
                                                     on_close=self.on_close)
                    self.ws.run_forever()
                except: time.sleep(5)
        t = threading.Thread(target=run)
        t.daemon = True
        t.start()

    def stop(self):
        """Stops the WebSocket stream."""
        print("🔌 WebSocket bağlantısı kapatılıyor...")
        self.keep_running = False
        if self.ws:
            self.ws.close()
