"""Chronological replay: decisions at close, entry at next candle open.

This replaces the divergent Backtrader order adapter. No input rows are
silently truncated, and no fill can read a later candle's close at entry.
"""
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pandas as pd

from app.analysis.strategy import SentinelStrategy, validate_candles
from app.core import config
from app.core.database import DatabaseManager
from app.core.models import decimal
from app.services.reporting import performance
from app.trading.paper_engine import PaperEngine


def load_data(path):
    frame = pd.read_csv(path)
    frame.columns = [c.strip().lower() for c in frame.columns]
    frame.rename(columns={'open time': 'timestamp', 'ts': 'timestamp', 'date': 'timestamp'}, inplace=True)
    if 'timestamp' not in frame:
        raise ValueError('CSV must have a timestamp column.')
    if pd.api.types.is_numeric_dtype(frame['timestamp']):
        unit = 'ms' if frame['timestamp'].iloc[0] > 1e11 else 's'
        frame['timestamp'] = pd.to_datetime(frame['timestamp'], unit=unit, utc=True)
    return validate_candles(frame)


def demo_candles(count=650):
    """Deterministic artificial prices for plumbing verification, not performance evidence."""
    rng = np.random.default_rng(27)
    step = np.arange(count)
    close = 30000 * np.exp(.0001 * step + .035 * np.sin(step / 18) + .002 * rng.normal(size=count))
    opening = np.r_[close[0], close[:-1]]
    return pd.DataFrame({'timestamp': pd.date_range('2026-01-01', periods=count, freq='h', tz='UTC'),
        'open': opening, 'high': np.maximum(opening, close) * 1.003,
        'low': np.minimum(opening, close) * .997, 'close': close,
        'volume': rng.uniform(100, 1000, count)})


def run_backtest(frame, settings, symbol='BTC/USDT', db_path=':memory:', mode='backtest'):
    settings = replace(settings, symbols=(symbol,), max_positions=1, telegram_enabled=False)
    frame = validate_candles(frame)
    if len(frame) <= config.WARMUP:
        raise ValueError(f'Need more than {config.WARMUP} candles.')
    strategy = SentinelStrategy(settings)
    prepared = strategy.prepare(frame)
    db = DatabaseManager(db_path, settings.initial_capital, mode=mode)
    try:
        if db.trades() or db._rows('SELECT 1 FROM paper_signals LIMIT 1'):
            raise ValueError('Replay needs an empty database. Choose a new --db path.')
        engine = PaperEngine(db, settings)
        peak, drawdown = db.initial_capital, decimal(0)
        for i in range(config.WARMUP, len(prepared)):
            bar = prepared.iloc[i]
            now = bar['timestamp'].isoformat()
            # i is the newly opening bar: only [0, i) is visible to the strategy.
            evaluation = strategy.evaluate(prepared.iloc[:i], symbol, prepared=True)
            engine.submit(evaluation, bar['open'], now)
            engine.on_bar(symbol, bar, now)
            equity = db.summary({symbol: bar['close']})['equity']
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak - equity) / peak)
        # Report a realized, cost-inclusive terminal result instead of hiding an open loss.
        final = prepared.iloc[-1]
        for trade in db.active_trades():
            db.exit_trade(trade['id'], final['close'], settings.fee_rate, settings.slippage,
                          'END_OF_DATA', timestamp=final['timestamp'].isoformat())
        report = performance(db)
        terminal = report['equity']
        peak = max(peak, terminal)
        drawdown = max(drawdown, (peak - terminal) / peak)
        report.update(mode=mode, symbol=symbol, timeframe=settings.timeframe,
            data_start=frame.iloc[0]['timestamp'].isoformat(),
            data_end=frame.iloc[-1]['timestamp'].isoformat(), rows=len(frame),
            warmup_candles=config.WARMUP, max_drawdown_pct=drawdown * 100,
            return_pct=(terminal / db.initial_capital - 1) * 100,
            fee_rate=settings.fee_rate, slippage=settings.slippage, leverage=settings.leverage,
            assumptions='Spot-price synthetic isolated margin; no funding/maintenance tiers; stop-first OHLC replay.',
            fills=db.fills())
        return report
    finally:
        db.close()


def save_report(report, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
