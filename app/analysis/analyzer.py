# analyzer.py
import pandas as pd
import numpy as np
from app.core import config

class MarketAnalyzer:
    def __init__(self):
        # --- AYARLAR ---
        self.rsi_period = 14
        self.ema_short = 50
        self.ema_long = 200
        self.atr_period = 14
        
        # MACD Ayarları
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        
        # OBV Slope Ayarı
        self.obv_slope_period = 7

        # --- DİNAMİK ZAMAN DİLİMİ AĞIRLIKLARI ---
        self.timeframe = config.TIMEFRAME
        self.weights = {
            'trend': 1.0,
            'momentum': 1.0,
            'mean_reversion': 1.0,
            'pivot': 1.0
        }
        
        # 1. SCALPING PROFILE ('1m', '3m', '5m', '15m')
        if self.timeframe in ['1m', '3m', '5m', '15m']:
            self.weights = {
                'trend': 0.5,        # Gürültü çok, trende az güven
                'momentum': 1.5,     # Hızlı hareketler önemli
                'mean_reversion': 2.0, # Fiyat çabuk döner
                'pivot': 1.2         # Pivot/Hacim
            }
        # 2. SWING PROFILE ('1d', '3d', '1w')
        elif self.timeframe in ['1d', '3d', '1w']:
            self.weights = {
                'trend': 2.0,        # Trend is King
                'momentum': 0.8,     # Osilatörler şişebilir
                'mean_reversion': 0.0, # Trend tersine dönmez
                'pivot': 1.0
            }
        # 3. DAY TRADING ('30m', '1h', '2h', '4h') - DEFAULT
        else:
            self.weights = {
                'trend': 1.0,
                'momentum': 1.0,
                'mean_reversion': 1.0,
                'pivot': 1.0
            }
        
        print(f"⚖️ Analyzer Ağırlıkları ({self.timeframe}): {self.weights}")

    def calculate_indicators(self, df: pd.DataFrame, pivot_data: dict = None) -> pd.DataFrame:
        """Gerekli tüm indikatörleri hesaplar (EMA, RSI, MACD, OBV, ATR, Pivots)."""
        # 1. HACİM ANALİZİ
        vol_mean = df['volume'].rolling(window=20).mean()
        vol_std = df['volume'].rolling(window=20).std()
        df['vol_z_score'] = (df['volume'] - vol_mean) / vol_std
        
        # 2. TREND (EMA)
        df['ema_50'] = df['close'].ewm(span=self.ema_short, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=self.ema_long, adjust=False).mean()
        
        # 3. MOMENTUM (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 4. MACD (Moving Average Convergence Divergence)
        ema_12 = df['close'].ewm(span=self.macd_fast, adjust=False).mean()
        ema_26 = df['close'].ewm(span=self.macd_slow, adjust=False).mean()
        df['macd_line'] = ema_12 - ema_26
        df['macd_signal'] = df['macd_line'].ewm(span=self.macd_signal, adjust=False).mean()
        df['macd_hist'] = df['macd_line'] - df['macd_signal']

        # 5. OBV (On-Balance Volume)
        # Kapanış > Önceki Kapanış => Hacmi Ekle, Tersi => Çıkar
        direction = np.where(df['close'] > df['close'].shift(1), 1, 
                             np.where(df['close'] < df['close'].shift(1), -1, 0))
        df['obv'] = (direction * df['volume']).cumsum()

        # 6. RİSK YÖNETİMİ (ATR)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(window=self.atr_period).mean()

        # 7. BOLLINGER BANDS & WIDTH (BBW)
        sma = df['close'].rolling(window=config.BB_LENGTH).mean()
        std = df['close'].rolling(window=config.BB_LENGTH).std()
        upper_band = sma + (std * config.BB_STD)
        lower_band = sma - (std * config.BB_STD)
        df['bbw'] = (upper_band - lower_band) / sma
        
        # 8. ADX (Trend Gücü)
        self._calculate_adx(df)

        # 9. FIBONACCI PIVOT POINTS (Multi-Timeframe)
        if pivot_data:
            high = pivot_data['high']
            low = pivot_data['low']
            close = pivot_data['close']
            
            # Pivot Formülü
            pivot = (high + low + close) / 3
            rng = high - low # Range
            
            # Pivot Levels
            df['pivot_p'] = pivot
            
            # Resistances
            df['pivot_r1'] = pivot + (0.382 * rng)
            df['pivot_r2'] = pivot + (0.618 * rng)
            df['pivot_r3'] = pivot + (1.000 * rng)
            
            # Supports
            df['pivot_s1'] = pivot - (0.382 * rng)
            df['pivot_s2'] = pivot - (0.618 * rng)
            df['pivot_s3'] = pivot - (1.000 * rng)
        else:
            # Veri yoksa 0 veya NaN bas (Hata almamak için)
            cols = ['pivot_p', 'pivot_r1', 'pivot_r2', 'pivot_r3', 'pivot_s1', 'pivot_s2', 'pivot_s3']
            for col in cols: df[col] = 0.0
        
        return df

    def _calculate_adx(self, df: pd.DataFrame):
        """Yardımcı fonksiyon: ADX hesaplar."""
        plus_dm = df['high'].diff()
        minus_dm = df['low'].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        
        tr1 = pd.DataFrame(df['high'] - df['low'])
        tr2 = pd.DataFrame(np.abs(df['high'] - df['close'].shift()))
        tr3 = pd.DataFrame(np.abs(df['low'] - df['close'].shift()))
        frames = [tr1, tr2, tr3]
        tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
        atr = tr.rolling(config.ADX_LENGTH).mean()
        
        plus_di = 100 * (plus_dm.ewm(alpha=1/config.ADX_LENGTH).mean() / atr)
        minus_di = 100 * (minus_dm.abs().ewm(alpha=1/config.ADX_LENGTH).mean() / atr)
        
        # Sıfıra bölünme hatasını önle
        sum_di = abs(plus_di + minus_di)
        sum_di = sum_di.replace(0, 1) 
        
        dx = (abs(plus_di - minus_di) / sum_di) * 100
        df['adx'] = dx.ewm(alpha=1/config.ADX_LENGTH).mean()

    def calculate_sentinel_score(self, df: pd.DataFrame) -> int:
        """
        Ağırlıklı Puanlama Sistemi (0-100)
        Trend (%30), Momentum (%40), Hacim (%30)
        """
        if len(df) < 50: return 50
        
        row = df.iloc[-1]
        score = 50.0  # Float ile başla, en son int yap
        
        # Gerekli verilerin varlığını kontrol et
        if pd.isna(row['ema_200']) or pd.isna(row['rsi']) or pd.isna(row['obv']):
            return 50

        # --- 1. TREND BİLEŞENİ (Ağırlık: %30 -> Max ±30 Puan) ---
        # Fiyat > EMA 200 => Bullish (+15)
        # Fiyat < EMA 200 => Bearish (-15)
        if row['close'] > row['ema_200']:
            score += 15
        else:
            score -= 15
            
        # Mean Reversion Cezası (Fiyat ortalamadan çok uzaksa)
        deviation = abs(row['close'] - row['ema_200']) / row['ema_200']
        if deviation > 0.05:
            if row['close'] > row['ema_200']: score -= 5  # Çok yükseldi, düzeltme gelebilir
            else: score += 5  # Çok düştü, tepki gelebilir

        # Golden/Death Cross (+10 / -10)
        # EMA 50, EMA 200'ü yukarı kestiyse (veya üzerindeyse)
        if row['ema_50'] > row['ema_200']:
            score += 10
        else:
            score -= 10

        # --- 2. MOMENTUM BİLEŞENİ (Ağırlık: %40 -> Max ±40 Puan) ---
        # RSI Check
        if row['rsi'] < 30: # Aşırı Satım -> Alım Fırsatı
            score += 15
        elif row['rsi'] > 70: # Aşırı Alım -> Satış Fırsatı
            score -= 15
            
        # MACD Crossover Check
        # MACD Line > Signal Line => Bullish (+15)
        if row['macd_line'] > row['macd_signal']:
            score += 15
        else:
            score -= 15
            
        # MACD Histogram Artışı (Momentum Hızlanıyor mu?)
        # Şimdilik sadece cross yeterli.

        # --- 3. PIVOT ANALİZİ (+/- 10-15 Puan) ---
        # --- 3. PIVOT ANALİZİ (ADX Destekli) ---
        # Trend Filtresi (Pivot Point'e göre)
        if 'pivot_p' in df.columns:
            pivot_p = row['pivot_p']
            pivot_r3 = row['pivot_r3']
            pivot_s3 = row['pivot_s3']
            current_adx = row['adx'] if 'adx' in row and not pd.isna(row['adx']) else 0
            
            # Veri NaN değilse ve 0 değilse
            if not pd.isna(pivot_p) and pivot_p > 0:
                # A. Trend Yönü (Coğrafi Konum)
                if row['close'] > pivot_p:
                    score += 10 # Boğalar Kontrolde
                else:
                    score -= 10 # Ayılar Kontrolde
                    
                # B. Uç Noktalar (R3/S3) - Reversal vs Breakout
                
                # R3 ÜZERİ (AŞIRI ALIM BÖLGESİ)
                if not pd.isna(pivot_r3) and row['close'] > pivot_r3:
                    # ADX > 30 ise Trend Çok Güçlü (Parabolik) -> Sakın Shortlama! (Puan Ekle)
                    if current_adx > 30:
                        score += 15 # Breakout Mode (Trend Takip)
                    else:
                        score -= 15 # Exhaustion Mode (Reversal Bekle)
                    
                # S3 ALTI (AŞIRI SATIM BÖLGESİ)
                if not pd.isna(pivot_s3) and row['close'] < pivot_s3:
                    # ADX > 30 ise Düşüş Çok Güçlü (Çöküș) -> Sakın Longlama! (Puan Kır)
                    if current_adx > 30:
                        score -= 15 # Crash Mode (Düşüş Takip)
                    else:
                        score += 15 # Oversold Mode (Tepki Bekle)

        # --- 4. HACİM BİLEŞENİ (Ağırlık: %30 -> Max ±30 Puan) ---
        # OBV Slope (Eğim) Hesaplama
        # Son N mumun lineer regresyonu
        obv_slice = df['obv'].iloc[-self.obv_slope_period:]
        y = obv_slice.values
        x = np.arange(len(y))
        
        # Eğim (Slope) hesapla
        try:
            slope, _ = np.polyfit(x, y, 1)
        except:
            slope = 0
            
        # Eğim Yönüne Göre Puanla
        if slope > 0: score += 15 # Hacim artıyor (Alıcılar baskın)
        else: score -= 15 # Hacim düşüyor veya satıcılar baskın
        
        # Uyumsuzluk (Divergence) Kontrolü (+10 / -10)
        # Fiyat Eğimi Hesapla
        price_slice = df['close'].iloc[-self.obv_slope_period:]
        p_slope, _ = np.polyfit(np.arange(len(price_slice)), price_slice.values, 1)
        
        # Bearish Divergence: Fiyat Artıyor (Slope > 0) AMA OBV Düşüyor (Slope < 0)
        if p_slope > 0 and slope < 0:
            score -= 10 # Gizli Satış (Negatif Uyumsuzluk)
            
        # Bullish Divergence: Fiyat Düşüyor (Slope < 0) AMA OBV Artıyor (Slope > 0)
        if p_slope < 0 and slope > 0:
            score += 10 # Gizli Alım (Pozitif Uyumsuzluk)

        return int(max(0, min(100, score)))

    def get_volatility_multiplier(self, df: pd.DataFrame) -> tuple[float, str]:
        """Piyasa Rejimini tespit eder ve TP/SL çarpanı döndürür."""
        if len(df) < 50: return 1.0, "NORMAL (Az Veri)"

        current_bbw = df['bbw'].iloc[-1]
        current_adx = df['adx'].iloc[-1]
        
        if pd.isna(current_bbw) or pd.isna(current_adx): return 1.0, "NORMAL (Eksik Veri)"

        lookback = min(len(df), config.BBW_LOOKBACK)
        history = df['bbw'].iloc[-lookback:]
        percentile_rank = history.rank(pct=True).iloc[-1]
        
        # 1. SQUEEZE (Sıkışma)
        if percentile_rank < 0.20 and current_adx < 20:
            return 0.6, "SQUEEZE (Sıkışma)"
            
        # 2. CHAOS (Kaos)
        atr_z_score = 0
        if 'atr' in df:
            atr_series = df['atr'].rolling(window=min(100, len(df))).mean()
            atr_std = df['atr'].rolling(window=min(100, len(df))).std()
            if not pd.isna(atr_std.iloc[-1]) and atr_std.iloc[-1] > 0:
                atr_z_score = (df['atr'].iloc[-1] - atr_series.iloc[-1]) / atr_std.iloc[-1]
        
        if percentile_rank > 0.90 or atr_z_score > 2.0:
            return 1.8, "CHAOS (Yüksek Volatilite)"

        # 3. TREND
        if 0.20 <= percentile_rank <= 0.80 and current_adx > 25:
            return 1.2, "TREND (Sağlıklı)" # Çarpanı biraz artırdım

        return 1.0, "NORMAL (Geçiş)"

    def check_signals(self, df, symbol):
        """
        Yeni Puanlama Sistemine Göre Sinyal Üretir.
        80-100: Güçlü Long, 0-20: Güçlü Short
        """
        signals = []
        last_row = df.iloc[-1]
        current_price = last_row['close']
        
        # 1. SKOR HESAPLA
        current_score = self.calculate_sentinel_score(df)
        
        atr = last_row['atr']
        if pd.isna(atr): atr = current_price * 0.01 
        
        # Sinyal Mesajı Şablonu
        msg_template = (
            "{icon} {symbol} İÇİN {direction} FIRSATI!\n"
            "⭐ Skor: {score}/100 ({strength})\n"
            "💰 Giriş: {price:.2f}\n"
            "🛑 Stop: {stop:.2f} | 🎯 Hedef: {target:.2f}"
        )

        # --- LONG SİNYALLERİ ---
        if current_score >= 60:
            direction = "LONG"
            icon = "🚀"
            strength = "GÜÇLÜ ALIM" if current_score >= 80 else "ZAYIF/TEPKİ ALIMI"
            
            # Stop Loss ve Target Hesapla (ATR Bazlı)
            # Güçlü sinyalde hedefi daha uzak tutabiliriz
            multiplier = 3.0 if current_score >= 80 else 2.0
            
            stop_loss = current_price - (2 * atr)
            target = current_price + (multiplier * atr)
            
            signals.append({
                'type': 'LONG_ENTRY',
                'symbol': symbol,
                'price': current_price,
                'score': current_score,
                'message': msg_template.format(
                    icon=icon, symbol=symbol, direction=direction,
                    score=current_score, strength=strength,
                    price=current_price, stop=stop_loss, target=target
                )
            })

        # --- SHORT SİNYALLERİ ---
        elif current_score <= 40:
            direction = "SHORT"
            icon = "🐻"
            strength = "GÜÇLÜ SATIŞ" if current_score <= 20 else "ZAYIF/TEPKİ SATIŞI"
            
            multiplier = 3.0 if current_score <= 20 else 2.0
            
            stop_loss = current_price + (2 * atr)
            target = current_price - (multiplier * atr)
            
            signals.append({
                'type': 'SHORT_ENTRY',
                'symbol': symbol,
                'price': current_price,
                'score': current_score,
                'message': msg_template.format(
                    icon=icon, symbol=symbol, direction=direction,
                    score=current_score, strength=strength,
                    price=current_price, stop=stop_loss, target=target
                )
            })

        # Ekstra: Hacim Anomalisini de raporlayabiliriz (Skora dahil ama görsel uyarı olarak iyi)
        if last_row['vol_z_score'] > 3:
             signals.append({
                'type': 'VOLUME_ANOMALY',
                'symbol': symbol,
                'price': current_price,
                'score': current_score,
                'message': f"🐳 {symbol} Balina Hareketi! (Hacim Patlaması)"
            })

        return signals, current_score