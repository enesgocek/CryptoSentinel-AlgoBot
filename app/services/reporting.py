"""Reports use actual ledger fills, including partial exits and every fee."""
from decimal import Decimal
from app.core.models import decimal


def performance(db, prices=None):
    result = db.summary(prices)
    totals = {}
    for fill in db.fills():
        totals[fill['trade_id']] = totals.get(fill['trade_id'], Decimal(0)) + decimal(fill['net_pnl'])
    closed = [t for t in db.trades() if t['status'] not in ('OPEN', 'MOONBAG')]
    result.update(closed_trades=len(closed),
                  wins=sum(totals.get(t['id'], Decimal(0)) > 0 for t in closed),
                  losses=sum(totals.get(t['id'], Decimal(0)) <= 0 for t in closed),
                  initial_capital=db.initial_capital)
    return result


def format_report(db, prices=None):
    r = performance(db, prices)
    return (
        f'CryptoSentinel | SANAL ISLEM\n'
        f'Serbest bakiye: {r["cash"]:.2f} USDT\n'
        f'Ayrilan marjin: {r["reserved_margin"]:.2f} USDT\n'
        f'Gerceklesmis net PnL: {r["realized_net_pnl"]:+.2f} USDT\n'
        f'Acik PnL: {r["unrealized_pnl"]:+.2f} USDT\n'
        f'Toplam ozsermaye: {r["equity"]:.2f} USDT\n'
        f'Komisyonlar: {r["fees"]:.2f} USDT\n'
        f'Acik: {r["active_positions"]} | Kapali: {r["closed_trades"]} | '
        f'Kazanc/kayip: {r["wins"]}/{r["losses"]}'
    )
