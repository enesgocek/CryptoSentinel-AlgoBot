"""One closed-candle strategy for live paper operation and replay."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from app.analysis.analyzer import MarketAnalyzer
from app.core import config
from app.core.models import TradePlan, decimal

OHLCV = ['open', 'high', 'low', 'close', 'volume']


def validate_candles(frame):
    required = {'timestamp', *OHLCV}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError('OHLCV columns or rows missing.')
    df = frame.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='raise')
    if df['timestamp'].isna().any() or df['timestamp'].duplicated().any() or not df['timestamp'].is_monotonic_increasing:
        raise ValueError('Candle timestamps must be unique and increasing.')
    df[OHLCV] = df[OHLCV].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(df[OHLCV].to_numpy(dtype=float)).all():
        raise ValueError('Non-finite market data.')
    if (df[['open','high','low','close']] <= 0).any().any() or (df['volume'] < 0).any():
        raise ValueError('Invalid price or volume.')
    if ((df['high'] < df[['open','close','low']].max(axis=1)) |
            (df['low'] > df[['open','close','high']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC prices.')
    return df.reset_index(drop=True)


@dataclass(frozen=True)
class Evaluation:
    candle: str
    score: int
    plan: TradePlan | None
    symbol: str = ''


class SentinelStrategy:
    def __init__(self, settings):
        self.settings = settings
        self.analyzer = MarketAnalyzer()

    def prepare(self, closed_candles):
        df = validate_candles(closed_candles)
        if not df['timestamp'].diff().dropna().eq(pd.Timedelta(self.settings.timeframe)).all():
            raise ValueError('Candle gaps or timeframe mismatch; repair the data before trading.')
        df = self.analyzer.calculate_indicators(df)
        # A completed higher-timeframe period is the only source for pivots.
        # Mapping each group to its previous group cannot expose future prices.
        frequency = 'MS' if self.settings.timeframe == '1d' else (
            'W-MON' if self.settings.timeframe in {'1h', '4h'} else '1D')
        indexed = df.set_index('timestamp')
        groups = indexed.resample(frequency, closed='left', label='left').agg(
            {'high': 'max', 'low': 'min', 'close': 'last'})
        if indexed.index[0] > groups.index[0]:
            groups.iloc[0] = np.nan  # The first fetched HTF period may be incomplete.
        groups = groups.shift(1)
        previous = groups.reindex(indexed.index, method='ffill')
        pivot = ((previous['high'] + previous['low'] + previous['close']) / 3).fillna(0).to_numpy()
        spread = (previous['high'] - previous['low']).fillna(0).to_numpy()
        df['pivot_p'] = pivot
        for n, ratio in enumerate((.382, .618, 1.), 1):
            df[f'pivot_r{n}'] = pivot + ratio * spread
            df[f'pivot_s{n}'] = pivot - ratio * spread
        return df

    def evaluate(self, closed_candles, symbol, prepared=False):
        df = closed_candles if prepared else self.prepare(closed_candles)
        if len(df) < config.WARMUP:
            return None
        row = df.iloc[-1]
        columns = ['ema_50', 'ema_200', 'rsi', 'macd_line', 'macd_signal', 'obv_slope', 'atr', 'adx', 'bbw']
        if not np.isfinite(row[columns].to_numpy(dtype=float)).all():
            return None
        candle = pd.Timestamp(row['timestamp']).isoformat()
        if row['atr'] <= 0 or row['volume'] <= 0:
            return Evaluation(candle, 50, None, symbol)
        score = self.analyzer.calculate_sentinel_score(row)
        if config.SCORE_SHORT_ENTRY < score < config.SCORE_LONG_ENTRY:
            return Evaluation(candle, score, None, symbol)
        side = 'LONG' if score >= config.SCORE_LONG_ENTRY else 'SHORT'
        multiplier, regime = self.analyzer.get_volatility_multiplier(df)
        # Keep the original bot's ROE targets; use them in BOTH execution modes.
        tp = self.settings.target_roe * decimal(multiplier) / self.settings.leverage
        tp = min(tp, decimal('.95'))  # A low-leverage short target must stay above zero.
        sl = self.settings.stop_roe * decimal(multiplier) / self.settings.leverage
        margin = self.settings.margin_high if score >= 80 or score <= 20 else self.settings.margin_medium
        pivot = decimal(row['pivot_r1' if side == 'LONG' else 'pivot_s1'])
        if pivot <= 0 or (side == 'LONG' and pivot <= decimal(row['close'])) or (side == 'SHORT' and pivot >= decimal(row['close'])):
            pivot = None
        return Evaluation(candle, score, TradePlan(symbol, candle, side, score,
            self.settings.leverage, margin, tp, sl, regime, pivot), symbol)
