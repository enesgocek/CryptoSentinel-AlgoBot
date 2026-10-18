import pandas as pd
import numpy as np
from app.core import config
from app.core.enums import MarketRegime

class MarketAnalyzer:
    def __init__(self):
        # Ayarlar config.py üzerinden alınıyor
        pass

    def calculate_indicators(self, df: pd.DataFrame, pivot_data: dict = None) -> pd.DataFrame:
        """Gerekli tüm indikatörleri hesaplar (EMA, RSI, MACD, OBV, ATR, Pivots)."""
        # 1. HACİM ANALİZİ
        vol_mean = df['volume'].rolling(window=20).mean()
        vol_std = df['volume'].rolling(window=20).std().replace(0, np.nan)
        df['vol_z_score'] = ((df['volume'] - vol_mean) / vol_std).fillna(0.0)

        # 2. TREND (EMA)
        df['ema_50'] = df['close'].ewm(span=config.EMA_SHORT, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=config.EMA_LONG, adjust=False).mean()

        # 3. MOMENTUM (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=config.RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=config.RSI_PERIOD).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = (100 - (100 / (1 + rs))).where(loss != 0, 100.0).where((gain != 0) | (loss != 0), 50.0)

        # 4. MACD
        ema_12 = df['close'].ewm(span=config.MACD_FAST, adjust=False).mean()
        ema_26 = df['close'].ewm(span=config.MACD_SLOW, adjust=False).mean()
        df['macd_line'] = ema_12 - ema_26
        df['macd_signal'] = df['macd_line'].ewm(span=config.MACD_SIGNAL, adjust=False).mean()
        df['macd_hist'] = df['macd_line'] - df['macd_signal']

        # 5. OBV
        direction = np.where(df['close'] > df['close'].shift(1), 1,
                             np.where(df['close'] < df['close'].shift(1), -1, 0))
        df['obv'] = (direction * df['volume']).cumsum()

        # --- YENİ: OBV Slope ve Uyumsuzluk (Pre-calculation) ---
        # apply içinde geçmiş veriye erişemeyeceğimiz için burada hesaplıyoruz.
        df['obv_slope'] = df['obv'].rolling(window=config.OBV_SLOPE_PERIOD).apply(self._calculate_slope, raw=True)
        df['price_slope'] = df['close'].rolling(window=config.OBV_SLOPE_PERIOD).apply(self._calculate_slope, raw=True)

        # Divergence Flag (1: Bullish, -1: Bearish, 0: None)
        df['divergence'] = 0
        # Bearish: Fiyat Artıyor (Slope > 0) AMA OBV Düşüyor (Slope < 0)
        df.loc[(df['price_slope'] > 0) & (df['obv_slope'] < 0), 'divergence'] = -1
        # Bullish: Fiyat Düşüyor (Slope < 0) AMA OBV Artıyor (Slope > 0)
        df.loc[(df['price_slope'] < 0) & (df['obv_slope'] > 0), 'divergence'] = 1

        # 6. ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(window=config.ATR_PERIOD).mean()

        # 7. BOLLINGER
        sma = df['close'].rolling(window=config.BB_LENGTH).mean()
        std = df['close'].rolling(window=config.BB_LENGTH).std()
        upper_band = sma + (std * config.BB_STD)
        lower_band = sma - (std * config.BB_STD)
        df['bbw'] = (upper_band - lower_band) / sma

        # 8. ADX
        self._calculate_adx(df)

        # 9. PIVOTS
        if pivot_data:
            high = pivot_data['high']
            low = pivot_data['low']
            close = pivot_data['close']
            pivot = (high + low + close) / 3
            rng = high - low

            df['pivot_p'] = pivot
            df['pivot_r1'] = pivot + (0.382 * rng)
            df['pivot_r2'] = pivot + (0.618 * rng)
            df['pivot_r3'] = pivot + (1.000 * rng)
            df['pivot_s1'] = pivot - (0.382 * rng)
            df['pivot_s2'] = pivot - (0.618 * rng)
            df['pivot_s3'] = pivot - (1.000 * rng)
        else:
            cols = ['pivot_p', 'pivot_r1', 'pivot_r2', 'pivot_r3', 'pivot_s1', 'pivot_s2', 'pivot_s3']
            for col in cols: df[col] = 0.0

        return df

    def _calculate_slope(self, y):
        """Rolling window için slope hesaplar."""
        x = np.arange(len(y))
        try:
            slope, _ = np.polyfit(x, y, 1)
            return slope
        except:
            return 0.0

    def _calculate_adx(self, df: pd.DataFrame):
        """Yardımcı fonksiyon: ADX hesaplar."""
        up = df['high'].diff()
        down = -df['low'].diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)

        tr1 = pd.DataFrame(df['high'] - df['low'])
        tr2 = pd.DataFrame(np.abs(df['high'] - df['close'].shift()))
        tr3 = pd.DataFrame(np.abs(df['low'] - df['close'].shift()))
        frames = [tr1, tr2, tr3]
        tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
        atr = tr.ewm(alpha=1/config.ADX_LENGTH, adjust=False).mean().replace(0, np.nan)

        plus_di = 100 * (plus_dm.ewm(alpha=1/config.ADX_LENGTH).mean() / atr)
        minus_di = 100 * (minus_dm.abs().ewm(alpha=1/config.ADX_LENGTH).mean() / atr)
        sum_di = abs(plus_di + minus_di).replace(0, 1)

        dx = (abs(plus_di - minus_di) / sum_di) * 100
        df['adx'] = dx.ewm(alpha=1/config.ADX_LENGTH).mean().fillna(0.0)


    def _get_dynamic_thresholds(self, row) -> tuple[float, float]:
        """
        Volatiliteye göre RSI eşiklerini dinamik ayarlar.
        BBW (Bollinger Band Width) arttıkça sınırlar genişler.
        """
        base_low = config.RSI_OVERSOLD
        base_high = config.RSI_OVERBOUGHT

        # Volatilite Çarpanı (bbw normalde 0.1-0.2 arasıdır, 0.5 üstü yüksektir)
        volatility_factor = row.get('bbw', 0.2)
        if pd.isna(volatility_factor): volatility_factor = 0.2

        # Eğer volatilite yüksekse, eşikleri esnet (Örn: 70 -> 75, 30 -> 25)
        # Factor 1.0 ise -> +10 puan esneme
        adaptive_shift = float(volatility_factor) * 20.0
        adaptive_shift = min(adaptive_shift, 15.0) # Max 15 puan kayma (85/15 sınırı)

        dynamic_high = base_high + adaptive_shift
        dynamic_low = base_low - adaptive_shift

        return dynamic_low, dynamic_high

    def _calculate_trend_score(self, row) -> float:
        score = 0
        # EMA Trend
        if row['close'] > row['ema_200']: score += config.SCORE_WEIGHT_TREND
        else: score -= config.SCORE_WEIGHT_TREND

        # Mean Reversion
        deviation = abs(row['close'] - row['ema_200']) / row['ema_200']
        if deviation > 0.05:
            if row['close'] > row['ema_200']: score -= config.SCORE_WEIGHT_REVERSAL
            else: score += config.SCORE_WEIGHT_REVERSAL

        # Cross
        if row['ema_50'] > row['ema_200']: score += config.SCORE_WEIGHT_CROSS
        else: score -= config.SCORE_WEIGHT_CROSS

        return score

    def _calculate_momentum_score(self, row, rsi_low, rsi_high) -> float:
        score = 0
        # RSI (Dinamik Eşikler)
        if row['rsi'] < rsi_low: score += config.SCORE_WEIGHT_MOMENTUM
        elif row['rsi'] > rsi_high: score -= config.SCORE_WEIGHT_MOMENTUM

        # MACD
        if row['macd_line'] > row['macd_signal']: score += config.SCORE_WEIGHT_MOMENTUM
        else: score -= config.SCORE_WEIGHT_MOMENTUM

        return score

    def _calculate_volume_score(self, row) -> float:
        score = 0
        # Slope (Calculate_indicators'da hesaplandı)
        slope = row.get('obv_slope', 0)
        if slope > 0: score += config.SCORE_WEIGHT_MOMENTUM
        else: score -= config.SCORE_WEIGHT_MOMENTUM

        # Divergence
        div = row.get('divergence', 0)
        if div == -1: score -= config.SCORE_WEIGHT_CROSS # Gizli Satış
        elif div == 1: score += config.SCORE_WEIGHT_CROSS # Gizli Alım

        return score

    def _calculate_pivot_score(self, row) -> float:
        score = 0
        if 'pivot_p' not in row or row['pivot_p'] == 0: return 0

        # Trend Yönü
        if row['close'] > row['pivot_p']: score += config.SCORE_WEIGHT_PIVOT
        else: score -= config.SCORE_WEIGHT_PIVOT

        # Breakout / Exhaustion
        adx = row.get('adx', 0)

        if row['close'] > row['pivot_r3']:
            if adx > 30: score += config.SCORE_WEIGHT_TREND
            else: score -= config.SCORE_WEIGHT_TREND

        if row['close'] < row['pivot_s3']:
            if adx > 30: score -= config.SCORE_WEIGHT_TREND
            else: score += config.SCORE_WEIGHT_TREND

        return score

    def get_volatility_multiplier(self, df: pd.DataFrame) -> tuple[float, str]:
        """Piyasa Rejimini tespit eder."""
        if len(df) < 50: return 1.0, MarketRegime.NORMAL_INSUFFICIENT.value

        current_bbw = df['bbw'].iloc[-1]
        current_adx = df['adx'].iloc[-1]

        if pd.isna(current_bbw) or pd.isna(current_adx): return 1.0, MarketRegime.NORMAL_INSUFFICIENT.value

        lookback = min(len(df), config.BBW_LOOKBACK)
        history = df['bbw'].iloc[-lookback:]
        percentile_rank = history.rank(pct=True).iloc[-1]

        # 1. SQUEEZE
        if percentile_rank < 0.20 and current_adx < 20:
            return 0.6, MarketRegime.SQUEEZE.value

        # 2. CHAOS
        atr_z_score = 0
        if 'atr' in df:
            atr_series = df['atr'].rolling(window=min(100, len(df))).mean()
            atr_std = df['atr'].rolling(window=min(100, len(df))).std()
            if not pd.isna(atr_std.iloc[-1]) and atr_std.iloc[-1] > 0:
                atr_z_score = (df['atr'].iloc[-1] - atr_series.iloc[-1]) / atr_std.iloc[-1]

        if percentile_rank > 0.90 or atr_z_score > 2.0:
            return 1.8, MarketRegime.CHAOS.value

        # 3. TREND
        if 0.20 <= percentile_rank <= 0.80 and current_adx > 25:
            return 1.2, MarketRegime.TREND.value

        return 1.0, MarketRegime.NORMAL.value

    def validate_data(self, df: pd.DataFrame, coin: str) -> bool:
        """
        Veri bütünlüğü kontrolü.
        Son 3 mumda kritik indikatörlerin (RSI, EMA, ADX vb.) hesaplanıp hesaplanmadığını kontrol eder.
        Eksik veri varsa False döner.
        """
        if df is None or len(df) < 50:
            print(f"⚠️ {coin}: Yetersiz veri ({len(df) if df is not None else 0} mum).")
            return False

        # Kontrol edilecek son mum sayısı (Son 2 mum kritik)
        check_df = df.iloc[-2:]

        critical_columns = [
            'close', 'high', 'low', 'volume',
            'ema_50', 'ema_200',
            'rsi', 'macd_line', 'macd_signal',
            'atr', 'adx', 'obv_slope'
        ]

        # DataFrame içinde bu kolonlar var mı?
        missing_cols = [col for col in critical_columns if col not in df.columns]
        if missing_cols:
             print(f"⚠️ {coin} Kritik Hata: Eksik Kolonlar -> {missing_cols}")
             return False

        # NaN Kontrolü
        if check_df[critical_columns].isnull().values.any():
            # Hangi kolon boş?
            null_counts = check_df[critical_columns].isnull().sum()
            bad_cols = null_counts[null_counts > 0].index.tolist()
            print(f"⚠️ {coin} VERİ HATASI: Kritik indikatörler hesaplanamadı! -> {bad_cols}")
            return False

        return True



    def calculate_sentinel_score(self, row: pd.Series, macro_stats: dict = None) -> int:
        """
        Calculates Trade Score (0-100).
        Drive base logic. Optional macro inputs require independently validated coefficients.
        """
        score = 50.0

        # 1. Trend (EMA)
        close = row['close']
        if close > row['ema_200']:
            score += 15 # Bullish Trend
        elif close < row['ema_200']:
            score -= 15 # Bearish Trend

        # Golden Cross
        if row['ema_50'] > row['ema_200']:
            score += 10

        # 2. Momentum (RSI)
        rsi_low = 30
        rsi_high = 70
        score += self._calculate_momentum_score(row, rsi_low, rsi_high)

        # MACD
        if row['macd_line'] > row['macd_signal']:
            score += 10
        else:
            score -= 10

        # 3. Volume
        score += self._calculate_volume_score(row)
        # 4. Pivot S/D
        score += self._calculate_pivot_score(row)

        # --- MULTI-TIMEFRAME MACRO STRATEGY ---
        # --- MULTI-TIMEFRAME MACRO STRATEGY ---
        if macro_stats:
            macro_z = macro_stats.get('macro_z', 0.0)
            mid_z = macro_stats.get('mid_z', 0.0)
            micro_z = macro_stats.get('micro_z', 0.0)

            # 1. MACRO IMPACT (Safety Net)
            if macro_z <= -1.5:
                score += 15
            elif macro_z >= 1.5:
                score -= 15

            # 2. MID IMPACT (Trend)
            if mid_z <= -1.2: # Relaxed from -1.5
                score += 10
            elif mid_z >= 1.5:
                score -= 5

            # 3. MICRO IMPACT (Trigger)
            if micro_z <= -1.5: # Relaxed from -1.8
                score += 10
            elif micro_z >= 1.8:
                score -= 5

            # 4. CONFLUENCE BONUS (Strong Conviction)
            if macro_z <= -1.0 and micro_z <= -1.5:
                score += 10

        # Limit Score
        return max(0, min(100, int(score)))
