"""SQLite paper ledger: decimal strings and atomic, idempotent fills.

No legacy PostgreSQL table is opened or migrated by this module.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import threading

from app.core.models import Fill, TradePlan, ZERO, decimal, utc_now


class DatabaseManager:
    def __init__(self, path=':memory:', initial_capital=Decimal('1000'), mode='paper'):
        self.path = str(path)
        if self.path != ':memory:':
            Path(self.path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('PRAGMA journal_mode=WAL')
        try:
            self._initialize(decimal(initial_capital), mode)
        except BaseException:
            self.conn.close()
            raise

    @contextmanager
    def transaction(self):
        with self._lock:
            self.conn.execute('BEGIN IMMEDIATE')
            try:
                yield self.conn
                self.conn.execute('COMMIT')
            except BaseException:
                self.conn.execute('ROLLBACK')
                raise

    def _initialize(self, initial, mode):
        if initial <= ZERO:
            raise ValueError('Initial capital must be positive.')
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS paper_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS paper_account(id INTEGER PRIMARY KEY CHECK(id=1), cash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS paper_trades(
                id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
                entry_price TEXT NOT NULL, quantity TEXT NOT NULL, remaining TEXT NOT NULL,
                initial_margin TEXT NOT NULL, margin TEXT NOT NULL, leverage INTEGER NOT NULL,
                stop TEXT NOT NULL, target TEXT NOT NULL, initial_target TEXT NOT NULL,
                pivot TEXT, tier TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN',
                tp1 INTEGER NOT NULL DEFAULT 0, pivot_done INTEGER NOT NULL DEFAULT 0,
                entry_time TEXT NOT NULL, exit_time TEXT, signal_candle TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS paper_one_active_symbol
                ON paper_trades(symbol) WHERE status IN ('OPEN','MOONBAG');
            CREATE TABLE IF NOT EXISTS paper_fills(
                id INTEGER PRIMARY KEY, trade_id INTEGER NOT NULL REFERENCES paper_trades(id),
                event_key TEXT UNIQUE NOT NULL, reason TEXT NOT NULL, price TEXT NOT NULL,
                quantity TEXT NOT NULL, gross_pnl TEXT NOT NULL, fee TEXT NOT NULL,
                net_pnl TEXT NOT NULL, timestamp TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS paper_signals(
                symbol TEXT NOT NULL, candle TEXT NOT NULL, score INTEGER NOT NULL,
                recorded_at TEXT NOT NULL, PRIMARY KEY(symbol,candle));
        ''')
        with self.transaction() as c:
            version = c.execute("SELECT value FROM paper_meta WHERE key='schema'").fetchone()
            if version and version[0] != '1':
                raise ValueError('Unsupported paper database version.')
            saved_mode = c.execute("SELECT value FROM paper_meta WHERE key='mode'").fetchone()
            if saved_mode and saved_mode[0] != mode:
                raise ValueError(f'Database belongs to {saved_mode[0]}, not {mode}. Use a separate --db.')
            c.execute("INSERT OR IGNORE INTO paper_meta VALUES('schema','1')")
            c.execute("INSERT OR IGNORE INTO paper_meta VALUES('mode',?)", (mode,))
            c.execute("INSERT OR IGNORE INTO paper_meta VALUES('initial_capital',?)", (str(initial),))
            c.execute('INSERT OR IGNORE INTO paper_account VALUES(1,?)', (str(initial),))

    def _rows(self, query, params=()):
        with self._lock:
            return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    @property
    def initial_capital(self):
        return decimal(self._rows("SELECT value FROM paper_meta WHERE key='initial_capital'")[0]['value'])

    def cash(self):
        return decimal(self._rows('SELECT cash FROM paper_account WHERE id=1')[0]['cash'])

    @staticmethod
    def _add_cash(c, change):
        current = decimal(c.execute('SELECT cash FROM paper_account WHERE id=1').fetchone()[0])
        c.execute('UPDATE paper_account SET cash=? WHERE id=1', (str(current + change),))

    def active_trades(self):
        return self._rows("SELECT * FROM paper_trades WHERE status IN ('OPEN','MOONBAG') ORDER BY id")

    def trades(self):
        return self._rows('SELECT * FROM paper_trades ORDER BY id')

    def fills(self):
        return self._rows('SELECT * FROM paper_fills ORDER BY id')

    def consume_signal(self, symbol, candle, score, timestamp=None):
        with self.transaction() as c:
            cursor = c.execute('INSERT OR IGNORE INTO paper_signals VALUES(?,?,?,?)',
                               (symbol, candle, int(score), timestamp or utc_now()))
            return cursor.rowcount == 1

    def open_trade(self, plan: TradePlan, reference_price, fee_rate, slippage,
                   timestamp=None, max_positions=3):
        reference = decimal(reference_price)
        fee_rate, slippage = decimal(fee_rate), decimal(slippage)
        if plan.side not in ('LONG', 'SHORT') or reference <= ZERO or plan.margin <= ZERO:
            raise ValueError('Invalid order.')
        if not (1 <= plan.leverage <= 50 and ZERO < plan.sl_move < Decimal(1) / plan.leverage
                and ZERO < plan.tp_move < 1):
            raise ValueError('Invalid leverage or target/stop distance.')
        if not (ZERO <= fee_rate < Decimal('.1') and ZERO <= slippage < Decimal('.1')):
            raise ValueError('Invalid execution costs.')
        sign = Decimal(1 if plan.side == 'LONG' else -1)
        price = reference * (1 + sign * slippage)
        quantity = plan.margin * plan.leverage / price
        fee = plan.margin * plan.leverage * fee_rate
        at = timestamp or utc_now()
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM paper_trades WHERE symbol=? AND status IN ('OPEN','MOONBAG')", (plan.symbol,)).fetchone():
                return None
            count = c.execute("SELECT COUNT(*) FROM paper_trades WHERE status IN ('OPEN','MOONBAG')").fetchone()[0]
            if count >= max_positions or decimal(c.execute('SELECT cash FROM paper_account WHERE id=1').fetchone()[0]) < plan.margin + fee:
                return None
            target = price * (1 + sign * plan.tp_move)
            stop = price * (1 - sign * plan.sl_move)
            cursor = c.execute('''INSERT INTO paper_trades
                (symbol,side,entry_price,quantity,remaining,initial_margin,margin,leverage,
                 stop,target,initial_target,pivot,tier,entry_time,signal_candle)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (plan.symbol, plan.side, str(price), str(quantity), str(quantity), str(plan.margin),
                 str(plan.margin), plan.leverage, str(stop), str(target), str(target),
                 str(plan.pivot) if plan.pivot is not None else None,
                 'HIGH' if plan.score >= 80 or plan.score <= 20 else 'MEDIUM', at, plan.candle))
            trade_id = cursor.lastrowid
            self._add_cash(c, -plan.margin - fee)
            c.execute('''INSERT INTO paper_fills
                (trade_id,event_key,reason,price,quantity,gross_pnl,fee,net_pnl,timestamp)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                (trade_id, f'{trade_id}:ENTRY', 'ENTRY', str(price), str(quantity), '0', str(fee), str(-fee), at))
            return trade_id

    def exit_trade(self, trade_id, reference_price, fee_rate, slippage, reason,
                   fraction=Decimal(1), timestamp=None):
        """Idempotent named exit; return margin + gross PnL - fee atomically."""
        reference, fraction = decimal(reference_price), decimal(fraction)
        fee_rate, slippage = decimal(fee_rate), decimal(slippage)
        if reference <= ZERO or not ZERO < fraction <= 1 or not reason or reason == 'ENTRY':
            raise ValueError('Invalid exit.')
        if not (ZERO <= fee_rate < Decimal('.1') and ZERO <= slippage < Decimal('.1')):
            raise ValueError('Invalid execution costs.')
        at = timestamp or utc_now()
        with self.transaction() as c:
            row = c.execute('SELECT * FROM paper_trades WHERE id=?', (trade_id,)).fetchone()
            if row is None or row['status'] not in ('OPEN', 'MOONBAG'):
                return None
            key = f'{trade_id}:{reason}'
            if c.execute('SELECT 1 FROM paper_fills WHERE event_key=?', (key,)).fetchone():
                return None
            sign = Decimal(1 if row['side'] == 'LONG' else -1)
            price = reference * (1 - sign * slippage)
            remaining, margin = decimal(row['remaining']), decimal(row['margin'])
            quantity = remaining * fraction
            released = margin * fraction
            gross = sign * (price - decimal(row['entry_price'])) * quantity
            fee = price * quantity * fee_rate
            # Approximate isolated margin: gaps cannot consume another trade's collateral.
            gross = max(gross, -released + fee)
            net = gross - fee
            new_remaining, new_margin = remaining - quantity, margin - released
            closed = fraction == 1
            stop = row['entry_price'] if reason in ('TP1', 'PIVOT') else row['stop']
            c.execute('''UPDATE paper_trades SET remaining=?,margin=?,stop=?,
                tp1=CASE WHEN ?='TP1' THEN 1 ELSE tp1 END,
                pivot_done=CASE WHEN ?='PIVOT' THEN 1 ELSE pivot_done END,
                status=?,exit_time=? WHERE id=?''',
                (str(new_remaining), str(new_margin), stop, reason, reason,
                 ('LIQUIDATED' if reason == 'LIQUIDATION' else 'CLOSED') if closed else row['status'],
                 at if closed else None, trade_id))
            self._add_cash(c, released + net)
            c.execute('''INSERT INTO paper_fills
                (trade_id,event_key,reason,price,quantity,gross_pnl,fee,net_pnl,timestamp)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                (trade_id, key, reason, str(price), str(quantity), str(gross), str(fee), str(net), at))
            return Fill(trade_id, reason, price, quantity, gross, fee, net)

    def recent_pnl(self, now=None, hours=24):
        at = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        cutoff = (at - timedelta(hours=hours)).isoformat()
        return sum((decimal(r['net_pnl']) for r in self._rows(
            'SELECT net_pnl FROM paper_fills WHERE timestamp>=? AND timestamp<=?', (cutoff, at.isoformat()))), ZERO)

    def summary(self, prices=None):
        prices = prices or {}
        cash, reserved, unrealized = self.cash(), ZERO, ZERO
        active = self.active_trades()
        for t in active:
            margin = decimal(t['margin'])
            reserved += margin
            price = decimal(prices.get(t['symbol'], t['entry_price']))
            sign = 1 if t['side'] == 'LONG' else -1
            unrealized += max(sign * (price - decimal(t['entry_price'])) * decimal(t['remaining']), -margin)
        fills = self.fills()
        net = sum((decimal(f['net_pnl']) for f in fills), ZERO)
        return {'cash': cash, 'reserved_margin': reserved, 'unrealized_pnl': unrealized,
                'equity': cash + reserved + unrealized, 'realized_net_pnl': net,
                'fees': sum((decimal(f['fee']) for f in fills), ZERO), 'active_positions': len(active)}

    def close(self):
        with self._lock:
            self.conn.close()
