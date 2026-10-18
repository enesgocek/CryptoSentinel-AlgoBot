from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from app.analysis.strategy import Evaluation
from app.core.config import Settings
from app.core.database import DatabaseManager
from app.core.models import TradePlan, decimal
from app.services.reporting import performance
from app.trading.paper_engine import PaperEngine


def plan(side='LONG', symbol='BTC/USDT', candle='2026-01-01T00:00:00+00:00'):
    return TradePlan(symbol, candle, side, 85 if side == 'LONG' else 15,
                     10, D(100), D('.1'), D('.05'))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager()
        self.addCleanup(self.db.close)

    def test_entry_reserves_margin_and_charges_notional_fee(self):
        trade = self.db.open_trade(plan(), 100, D('.001'), D(0))
        self.assertIsNotNone(trade)
        self.assertEqual(self.db.cash(), D(899))
        summary = self.db.summary()
        self.assertEqual(summary['reserved_margin'], D(100))
        self.assertEqual(summary['equity'], D(999))
        self.assertEqual(summary['fees'], D(1))

    def test_partial_then_final_exit_has_exact_cash_and_realized_pnl(self):
        trade = self.db.open_trade(plan(), 100, D('.001'), D(0))
        half = self.db.exit_trade(trade, 110, D('.001'), D(0), 'TP1', D('.5'))
        self.assertEqual(half.net_pnl, D('49.45'))
        self.assertEqual(self.db.cash(), D('998.45'))
        self.assertEqual(decimal(self.db.active_trades()[0]['margin']), D(50))
        self.assertIsNone(self.db.exit_trade(trade, 110, D('.001'), D(0), 'TP1', D('.5')))
        self.db.exit_trade(trade, 120, D('.001'), D(0), 'TARGET')
        self.assertEqual(self.db.cash(), D('1147.85'))
        self.assertEqual(self.db.recent_pnl(), D('147.85'))
        self.assertEqual(performance(self.db)['wins'], 1)
        self.assertEqual(self.db.summary()['reserved_margin'], 0)

    def test_short_slippage_and_fees_are_adverse(self):
        trade = self.db.open_trade(plan('SHORT'), 100, D('.001'), D('.001'))
        row = self.db.active_trades()[0]
        self.assertEqual(decimal(row['entry_price']), D('99.900'))
        fill = self.db.exit_trade(trade, 90, D('.001'), D('.001'), 'TARGET')
        self.assertEqual(fill.price, D('90.090'))
        expected = (D('99.9') - D('90.09')) * decimal(row['quantity']) - fill.fee - D(1)
        self.assertAlmostEqual(self.db.cash(), D(1000) + expected, places=20)

    def test_insufficient_cash_includes_entry_fee(self):
        huge = replace(plan(), margin=D(1000))
        self.assertIsNone(self.db.open_trade(huge, 100, D('.001'), D(0)))
        self.assertEqual(self.db.cash(), D(1000))
        self.assertEqual(self.db.fills(), [])

    def test_duplicate_symbol_and_position_limit_do_not_spend_cash(self):
        self.db.open_trade(plan(), 100, D(0), D(0))
        self.assertIsNone(self.db.open_trade(plan(), 100, D(0), D(0)))
        self.assertIsNone(self.db.open_trade(plan(symbol='ETH/USDT'), 100, D(0), D(0), max_positions=1))
        self.assertEqual(self.db.cash(), 900)

    def test_transaction_rolls_back_cash_trade_and_fill_together(self):
        self.db.conn.execute("CREATE TRIGGER reject_fill BEFORE INSERT ON paper_fills BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(Exception):
            self.db.open_trade(plan(), 100, D('.001'), D(0))
        self.assertEqual(self.db.cash(), 1000)
        self.assertEqual(self.db.trades(), [])
        self.assertEqual(self.db.fills(), [])

    def test_exit_transaction_rolls_back_on_storage_failure(self):
        trade = self.db.open_trade(plan(), 100, D(0), D(0))
        self.db.conn.execute("CREATE TRIGGER reject_exit BEFORE INSERT ON paper_fills WHEN NEW.reason != 'ENTRY' BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(Exception):
            self.db.exit_trade(trade, 110, D(0), D(0), 'TARGET')
        self.assertEqual(self.db.cash(), 900)
        self.assertEqual(len(self.db.active_trades()), 1)
        self.assertEqual(len(self.db.fills()), 1)

    def test_concurrent_duplicate_close_is_paid_once(self):
        trade = self.db.open_trade(plan(), 100, D(0), D(0))
        with ThreadPoolExecutor(2) as pool:
            fills = list(pool.map(lambda _: self.db.exit_trade(trade, 110, D(0), D(0), 'TARGET'), range(2)))
        self.assertEqual(sum(f is not None for f in fills), 1)
        self.assertEqual(self.db.cash(), 1100)

    def test_daily_loss_uses_partial_fills_and_entry_fees(self):
        settings = replace(Settings(), daily_loss=D(10), fee_rate=D(0), slippage=D(0))
        trade = self.db.open_trade(plan(), 100, D(0), D(0))
        self.db.exit_trade(trade, 95, D(0), D(0), 'STOP', D('.5'))
        self.assertEqual(self.db.recent_pnl(), D(-25))
        engine = PaperEngine(self.db, settings)
        other = plan(symbol='ETH/USDT')
        self.assertIsNone(engine.submit(Evaluation(other.candle, other.score, other), 100))
        self.assertEqual(len(self.db.trades()), 1)

    def test_stop_before_target_and_tp1_on_ambiguous_bar(self):
        settings = replace(Settings(), fee_rate=D(0), slippage=D(0))
        trade = self.db.open_trade(plan(), 100, D(0), D(0))
        fills = PaperEngine(self.db, settings).on_bar('BTC/USDT', {'open':100,'low':90,'high':120,'close':110})
        self.assertEqual([f.reason for f in fills], ['STOP'])
        self.assertEqual(fills[0].price, D(95))
        self.assertEqual(self.db.cash(), D(950))

    def test_gap_loss_is_capped_at_isolated_collateral(self):
        trade = self.db.open_trade(plan(), 100, D('.001'), D(0))
        self.db.exit_trade(trade, 50, D('.001'), D(0), 'LIQUIDATION')
        self.assertEqual(self.db.cash(), D(899))
        self.assertEqual(self.db.trades()[0]['status'], 'LIQUIDATED')

    def test_final_target_on_single_tick_exits_without_waiting_for_tp1(self):
        trade = self.db.open_trade(plan(), 100, D(0), D(0))
        fills = PaperEngine(self.db, replace(Settings(), fee_rate=D(0), slippage=D(0))).on_price('BTC/USDT', 111)
        self.assertEqual([f.reason for f in fills], ['TARGET'])
        self.assertEqual(self.db.active_trades(), [])

    def test_reopen_keeps_balance_positions_and_signal_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'paper.sqlite3'
            first = DatabaseManager(path)
            first.consume_signal('BTC/USDT', 'candle', 80)
            first.open_trade(plan(), 100, D('.001'), D(0))
            first.close()
            second = DatabaseManager(path, D(5000))
            try:
                self.assertEqual(second.initial_capital, D(1000))
                self.assertEqual(second.cash(), D(899))
                self.assertEqual(len(second.active_trades()), 1)
                self.assertFalse(second.consume_signal('BTC/USDT', 'candle', 80))
            finally:
                second.close()

    def test_modes_cannot_share_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'paper.sqlite3'
            first = DatabaseManager(path, mode='demo')
            first.close()
            with self.assertRaisesRegex(ValueError, 'belongs to demo'):
                DatabaseManager(path, mode='paper')

    def test_same_candle_cannot_reopen_after_a_close(self):
        settings = replace(Settings(), fee_rate=D(0), slippage=D(0))
        engine = PaperEngine(self.db, settings)
        p = plan()
        evaluation = Evaluation(p.candle, p.score, p)
        first = engine.submit(evaluation, 100)
        self.assertIsNotNone(first)
        self.db.exit_trade(first, 110, D(0), D(0), 'TARGET')
        self.assertIsNone(engine.submit(evaluation, 100))
        self.assertEqual(len(self.db.trades()), 1)

    def test_short_stop_and_profit_have_correct_directions(self):
        engine = PaperEngine(self.db, replace(Settings(), fee_rate=D(0), slippage=D(0)))
        first = self.db.open_trade(plan('SHORT'), 100, D(0), D(0))
        stopped = engine.on_price('BTC/USDT', 106)
        self.assertEqual(stopped[0].reason, 'STOP')
        self.assertEqual(self.db.cash(), D(940))
        self.db.open_trade(plan('SHORT', candle='next'), 100, D(0), D(0))
        won = engine.on_price('BTC/USDT', 89)
        self.assertEqual(won[0].reason, 'TARGET')
        self.assertEqual(self.db.cash(), D(1050))

    def test_partial_profit_is_not_lost_in_report_when_runner_stops(self):
        engine = PaperEngine(self.db, replace(Settings(), fee_rate=D('.001'), slippage=D(0)))
        self.db.open_trade(plan(), 100, D('.001'), D(0))
        self.assertEqual(engine.on_price('BTC/USDT', 106)[0].reason, 'TP1')
        self.assertEqual(engine.on_price('BTC/USDT', 100)[0].reason, 'STOP')
        report = performance(self.db)
        self.assertEqual(report['wins'], 1)
        self.assertEqual(report['realized_net_pnl'], D('27.97'))
        self.assertEqual(report['cash'], D('1027.97'))
