from enum import Enum, auto

class TradeStatus(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"
    MOONBAG = "MOONBAG"

class PositionType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class SignalType(Enum):
    LONG_ENTRY = "LONG_ENTRY"
    SHORT_ENTRY = "SHORT_ENTRY"
    NO_SIGNAL = "NO_SIGNAL"

class MarketRegime(Enum):
    SQUEEZE = "SQUEEZE (Sıkışma)"
    CHAOS = "CHAOS (Yüksek Volatilite)"
    TREND = "TREND (Sağlıklı)"
    NORMAL = "NORMAL (Trend)"
    NORMAL_TRANSITION = "NORMAL (Geçiş)"
    NORMAL_INSUFFICIENT = "NORMAL (Az Veri)"
