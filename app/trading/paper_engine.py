"""Synchronous deterministic paper execution shared by live ticks and replay."""
from decimal import Decimal
from app.core.models import ZERO, decimal


class PaperEngine:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    def submit(self, evaluation, price, now=None):
        if evaluation is None:
            return None
        # Consume every evaluated candle even if there is no entry, insufficient
        # cash, an existing position or a circuit breaker. This survives restarts.
        plan = evaluation.plan
        symbol = evaluation.symbol or (plan.symbol if plan else None)
        if symbol is None:
            return None
        if not self.db.consume_signal(symbol, evaluation.candle, evaluation.score, now):
            return None
        if plan is None:
            return None
        pnl = self.db.recent_pnl(now)
        if pnl <= -self.settings.daily_loss or pnl >= self.settings.daily_profit:
            return None
        return self.db.open_trade(plan, price, self.settings.fee_rate, self.settings.slippage,
                                  now, self.settings.max_positions)

    def _exit(self, trade, price, reason, fraction=Decimal(1), now=None):
        return self.db.exit_trade(trade['id'], price, self.settings.fee_rate,
                                  self.settings.slippage, reason, fraction, now)

    def on_price(self, symbol, price, now=None):
        price = decimal(price)
        if price <= ZERO:
            raise ValueError('Invalid tick price.')
        fills = []
        for t in self.db.active_trades():
            if t['symbol'] != symbol:
                continue
            entry, stop, target = map(decimal, (t['entry_price'], t['stop'], t['target']))
            long = t['side'] == 'LONG'
            change = (price - entry) / entry * (1 if long else -1)
            # Approximate isolated liquidation, not Binance's maintenance tiers.
            if change * t['leverage'] <= -1:
                fill = self._exit(t, price, 'LIQUIDATION', now=now)
            elif (long and price <= stop) or (not long and price >= stop):
                fill = self._exit(t, price, 'STOP', now=now)
            elif (long and price >= target) or (not long and price <= target):
                # A crossed final target exits everything immediately, even if
                # a sparse tick feed skipped TP1. Do not postpone the exit.
                fill = self._exit(t, price, 'TARGET', now=now)
            elif not t['tp1'] and abs(price - entry) >= abs(decimal(t['initial_target']) - entry) / 2 and change > 0:
                fill = self._exit(t, price, 'TP1', Decimal('.5'), now)
            elif not t['pivot_done'] and t['pivot'] and change * t['leverage'] >= Decimal('.15') and (
                    (long and price >= decimal(t['pivot'])) or (not long and price <= decimal(t['pivot']))):
                fraction = Decimal('.25') if t['tier'] == 'HIGH' else Decimal('.5')
                fill = self._exit(t, price, 'PIVOT', fraction, now)
            else:
                fill = None
            if fill:
                fills.append(fill)
        return fills

    def on_bar(self, symbol, bar, now=None):
        """Conservative OHLC replay: gap open first, then stop before profit.

        Intrabar path is unknowable. A bar crossing both levels is a stop.
        After TP1 moves a stop, only the next bar can trigger that new stop.
        """
        fills = self.on_price(symbol, bar['open'], now)
        for t in self.db.active_trades():
            if t['symbol'] != symbol:
                continue
            long = t['side'] == 'LONG'
            stop, target = decimal(t['stop']), decimal(t['target'])
            low, high = decimal(bar['low']), decimal(bar['high'])
            if (long and low <= stop) or (not long and high >= stop):
                fill = self._exit(t, stop, 'STOP', now=now)
                if fill:
                    fills.append(fill)
            elif (long and high >= target) or (not long and low <= target):
                fill = self._exit(t, target, 'TARGET', now=now)
                if fill:
                    fills.append(fill)
            else:
                entry = decimal(t['entry_price'])
                tp1 = entry + (decimal(t['initial_target']) - entry) / 2
                if not t['tp1'] and ((long and high >= tp1) or (not long and low <= tp1)):
                    fill = self._exit(t, tp1, 'TP1', Decimal('.5'), now)
                    if fill:
                        fills.append(fill)
                elif t['pivot'] and not t['pivot_done']:
                    pivot = decimal(t['pivot'])
                    hit = (long and high >= pivot) or (not long and low <= pivot)
                    roe = (pivot - entry) / entry * t['leverage'] * (1 if long else -1)
                    if hit and roe >= Decimal('.15'):
                        fill = self._exit(t, pivot, 'PIVOT', Decimal('.25') if t['tier']=='HIGH' else Decimal('.5'), now)
                        if fill:
                            fills.append(fill)
        return fills
