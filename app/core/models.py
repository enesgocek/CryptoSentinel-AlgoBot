"""Domain values shared by live paper trading and historical replay."""
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone

ZERO = Decimal('0')


def decimal(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Non-finite monetary value.')
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    candle: str
    side: str
    score: int
    leverage: int
    margin: Decimal
    tp_move: Decimal
    sl_move: Decimal
    regime: str = 'NORMAL'
    pivot: Decimal | None = None


@dataclass(frozen=True)
class Fill:
    trade_id: int
    reason: str
    price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    fee: Decimal
    net_pnl: Decimal
