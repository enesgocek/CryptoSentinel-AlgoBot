# telegram_bot.py
import requests
from app.core import config 
import time  # Zaman takibi için gerekli


class TelegramBot:
    def __init__(self):
        """
        Botun kimlik, adres bilgileri ve Sinyal Hafızasını hazırlar.
        """
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        
        # --- SPAM ENGELLEYİCİ AYARLARI ---
        # Hangi coine en son ne zaman mesaj attık?
        # Yapı: {'BTC/USDT': {'type': 'SHORT', 'time': 1708543210}}
        self.last_signals = {} 
        
        # Aynı sinyal için kaç saniye sessiz kalalım? (300 sn = 5 Dakika)
        self.cooldown_period = 300 

    def send_message(self, message, symbol=None, signal_type=None):
        """
        Belirtilen mesajı Telegram'a gönderir.
        Eğer symbol ve signal_type verilirse SPAM kontrolü yapar.
        """
        # --- SPAM KONTROLÜ ---
        if symbol and signal_type:
            current_time = time.time()
            
            # Bu coin hafızada var mı?
            if symbol in self.last_signals:
                last_signal = self.last_signals[symbol]
                
                # Eğer sinyal TİPİ aynıysa (Yine SHORT ise) VE süre dolmamışsa
                if last_signal['type'] == signal_type:
                    time_passed = current_time - last_signal['time']
                    
                    if time_passed < self.cooldown_period:
                        remaining = int(self.cooldown_period - time_passed)
                        print(f"   🔕 {symbol} için '{signal_type}' bildirimi filtrelendi. ({remaining} sn kaldı)")
                        return # Fonksiyondan çık, mesaj GÖNDERME.

            # Hafızayı Güncelle (Yeni sinyali kaydet)
            self.last_signals[symbol] = {
                'type': signal_type,
                'time': current_time
            }

        # --- GÖNDERME İŞLEMİ ---
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(self.base_url, data=payload)
            
            if response.status_code == 200:
                print("   ✅ Bildirim gönderildi.")
            else:
                print(f"   ⚠️ Bildirim hatası: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Bağlantı hatası: {e}")