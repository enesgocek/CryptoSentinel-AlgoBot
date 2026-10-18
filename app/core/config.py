"""Local paper settings. Never search backups for credentials."""
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import re

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env', override=False)

# Indicator/scoring parameters retained from the Drive version.
TIMEFRAME = '1h'
RSI_PERIOD = ADX_LENGTH = ATR_PERIOD = 14
RSI_OVERBOUGHT, RSI_OVERSOLD = 70, 30
EMA_SHORT, EMA_LONG = 50, 200
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
OBV_SLOPE_PERIOD = 7
BB_LENGTH, BB_STD, BBW_LOOKBACK = 20, 2.0, 100
SCORE_LONG_ENTRY, SCORE_SHORT_ENTRY = 55, 45
SCORE_HIGH_THRESHOLD, SCORE_LOW_THRESHOLD = 80, 20
SCORE_WEIGHT_TREND, SCORE_WEIGHT_CROSS = 15, 10
SCORE_WEIGHT_MOMENTUM, SCORE_WEIGHT_PIVOT, SCORE_WEIGHT_REVERSAL = 15, 10, 5
WARMUP = 200


@dataclass(frozen=True)
class Settings:
    symbols: tuple[str, ...] = ('BTC/USDT', 'ETH/USDT', 'BNB/USDT')
    timeframe: str = '1h'
    db_path: str = str(ROOT / 'data' / 'paper.sqlite3')
    initial_capital: Decimal = Decimal('1000')
    leverage: int = 25
    margin_high: Decimal = Decimal('100')
    margin_medium: Decimal = Decimal('75')
    target_roe: Decimal = Decimal('0.60')
    stop_roe: Decimal = Decimal('0.30')
    fee_rate: Decimal = Decimal('0.001')
    slippage: Decimal = Decimal('0.0005')
    daily_loss: Decimal = Decimal('100')
    daily_profit: Decimal = Decimal('250')
    max_positions: int = 3
    poll_seconds: float = 30
    price_poll_seconds: float = 5
    stale_seconds: float = 30
    request_timeout: float = 15
    telegram_enabled: bool = False
    telegram_token: str = ''
    telegram_chat_id: str = ''
    api_base: str = 'https://data-api.binance.vision'
    ws_base: str = 'wss://data-stream.binance.vision/stream'

    def __post_init__(self):
        if not self.symbols or any(not re.fullmatch(r'[A-Z0-9]+/USDT', s) for s in self.symbols):
            raise ValueError('SYMBOLS must contain pairs such as BTC/USDT.')
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError('Duplicate symbols are not allowed.')
        if self.timeframe not in {'1m', '5m', '15m', '30m', '1h', '4h', '1d'}:
            raise ValueError('Unsupported timeframe.')
        for name in ('initial_capital', 'margin_high', 'margin_medium', 'target_roe',
                     'stop_roe', 'daily_loss', 'daily_profit'):
            value = getattr(self, name)
            if not value.is_finite() or value <= 0:
                raise ValueError(f'{name} must be a finite positive number.')
        if not 1 <= self.leverage <= 50 or not 1 <= self.max_positions <= 100:
            raise ValueError('Invalid leverage or position limit.')
        for name in ('fee_rate', 'slippage'):
            value = getattr(self, name)
            if not value.is_finite() or not Decimal('0') <= value < Decimal('0.1'):
                raise ValueError(f'Invalid {name}.')
        if self.stop_roe >= 1 or self.target_roe >= self.leverage:
            raise ValueError('Stops must precede liquidation and short targets must be positive.')
        import math
        for name in ('poll_seconds', 'price_poll_seconds', 'stale_seconds', 'request_timeout'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'Invalid {name}.')
        if self.telegram_enabled and not (self.telegram_token and self.telegram_chat_id):
            raise ValueError('Telegram enabled but token/chat ID missing.')

    @classmethod
    def from_env(cls):
        return cls(
            symbols=tuple(s.strip().upper() for s in os.getenv('SYMBOLS', 'BTC/USDT,ETH/USDT,BNB/USDT').split(',')),
            timeframe=os.getenv('TIMEFRAME', '1h'),
            db_path=os.getenv('PAPER_DB_PATH', str(ROOT / 'data' / 'paper.sqlite3')),
            initial_capital=Decimal(os.getenv('INITIAL_CAPITAL', '1000')),
            leverage=int(os.getenv('PAPER_LEVERAGE', '25')),
            fee_rate=Decimal(os.getenv('FEE_RATE', '0.001')),
            slippage=Decimal(os.getenv('SLIPPAGE_RATE', '0.0005')),
            poll_seconds=float(os.getenv('ANALYSIS_INTERVAL', '30')),
            telegram_enabled=os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true',
            telegram_token=os.getenv('TELEGRAM_TOKEN', ''),
            telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', ''),
        )
