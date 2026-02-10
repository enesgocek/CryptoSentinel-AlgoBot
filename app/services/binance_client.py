import ccxt
import pandas as pd
from app.core import config  # Ayarlar dosyamızı çağırdık


class BinanceClient:
    def __init__(self):
        """
        Binance bağlantısını başlatan kurucu metod.
        """
        # Binance'e bağlanıyoruz (API Key olmadan public veri çekebiliriz)
        self.exchange = ccxt.binance({
            'enableRateLimit': True,  # Ban yememek için hız sınırı koyar
        })

    def get_ohlcv(self, symbol):
        """
        Belirtilen coin için Mum (OHLCV) verilerini çeker ve tabloya çevirir.
        
        Args:
            symbol (str): Coin çifti (Örn: 'BTC/USDT')
            
        Returns:
            pd.DataFrame: İşlenmiş veri tablosu
        """
        try:
            # 1. Binance'den ham veriyi çek
            # fetch_ohlcv fonksiyonu: Open, High, Low, Close, Volume getirir
            bars = self.exchange.fetch_ohlcv(
                symbol, 
                timeframe=config.TIMEFRAME, 
                limit=config.LIMIT
            )

            # 2. Veriyi Pandas DataFrame'e (Tabloya) çevir [cite: 138]
            # ccxt veriyi liste olarak verir, biz bunu Excel gibi sütunlara ayırıyoruz
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # 3. Zaman damgasını (timestamp) okunabilir tarihe çevir
            # Örn: 167890000 -> 2026-02-06 14:00:00
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            return df

        except Exception as e:
            print(f"Hata oluştu ({symbol}): {e}")
            return None

    def get_pivot_data(self, symbol):
        """
        Fibonacci Pivot Hesabı için Üst Zaman Diliminin (HTF)
        Önceki mum verilerini (High, Low, Close) getirir.
        """
        # 1. Zaman Dilimi Eşleşmesi
        htf = '1d' # Varsayılan: Günlük
        
        if config.TIMEFRAME in ['1m', '5m', '15m']:
            htf = '1d' # Günlük Pivotlar
        elif config.TIMEFRAME in ['1h', '4h']:
            htf = '1w' # Haftalık Pivotlar
        elif config.TIMEFRAME == '1d':
            htf = '1M' # Aylık Pivotlar
            
        try:
            # 2. HTF Verisini Çek (Sadece son 2 mum yeterli)
            # Limit=2 alıyoruz çünkü [0] -> Tamamlanmamış mum, [1] -> Tamamlanmış (önceki) mum olabilir
            # Ancak ccxt sıralaması eskiye -> yeniye doğru:
            # [-1] -> Şu anki (canlı) mum
            # [-2] -> Önceki kapanmış mum
            
            bars = self.exchange.fetch_ohlcv(symbol, timeframe=htf, limit=5)
            if not bars or len(bars) < 2: return None
            
            # DataFrame'e çevir
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # [-2] numaralı satırı (önceki kapanmış mum) al
            prev_candle = df.iloc[-2]
            
            return {
                'high': prev_candle['high'],
                'low': prev_candle['low'],
                'close': prev_candle['close']
            }
            
        except Exception as e:
            print(f"⚠️ Pivot Verisi Hatası ({symbol}): {e}")
            return None