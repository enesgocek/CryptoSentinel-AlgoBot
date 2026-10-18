import asyncio
from dataclasses import replace
from decimal import Decimal as D
import json
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from app.analysis.strategy import SentinelStrategy, validate_candles
from app.backtesting.backtest_engine import demo_candles, run_backtest
from app.core.config import Settings
from app.core.database import DatabaseManager
from app.services.binance_client import BinanceClient
from app.trading.bot import CryptoSentinelBot
from app.trading.stream_manager import StreamManager


class StrategyTests(unittest.TestCase):
    def test_future_prices_cannot_change_past_indicators_pivots_or_score(self):
        settings = Settings()
        strategy = SentinelStrategy(settings)
        original = demo_candles(500)
        altered = original.copy()
        altered.loc[350:, ['open','high','low','close']] *= 3
        before = strategy.prepare(original)
        after = strategy.prepare(altered)
        assert_frame_equal(before.iloc[:350], after.iloc[:350])
        self.assertEqual(strategy.evaluate(before.iloc[:350], 'BTC/USDT', prepared=True),
                         strategy.evaluate(after.iloc[:350], 'BTC/USDT', prepared=True))

    def test_replay_executes_full_cycle_and_reconciles_fills(self):
        result = run_backtest(demo_candles(400), Settings())
        self.assertGreater(result['closed_trades'], 0)
        self.assertEqual(result['active_positions'], 0)
        total = sum((D(f['net_pnl']) for f in result['fills']), D(0))
        self.assertAlmostEqual(result['equity'], D(1000) + total, places=20)
        self.assertEqual(result['rows'], 400)

    def test_replay_entry_is_next_open_not_next_close(self):
        result = run_backtest(demo_candles(220), replace(Settings(), slippage=D(0)))
        self.assertTrue(result['fills'])
        frame = demo_candles(220).set_index('timestamp')
        for fill in result['fills']:
            if fill['reason'] == 'ENTRY':
                price = frame.loc[pd.Timestamp(fill['timestamp']), 'open']
                self.assertEqual(D(fill['price']), D(str(price)))

    def test_flat_prices_and_zero_volume_have_finite_ready_indicators(self):
        frame = demo_candles(220)
        frame[['open','high','low','close']] = 100
        frame['volume'] = 0
        strategy = SentinelStrategy(Settings())
        prepared = strategy.prepare(frame)
        evaluation = strategy.evaluate(prepared, 'BTC/USDT', prepared=True)
        self.assertIsNotNone(evaluation)
        self.assertEqual(evaluation.score, 50)
        self.assertIsNone(evaluation.plan)
        self.assertTrue(np.isfinite(prepared.iloc[-1][['rsi','adx','vol_z_score']].astype(float)).all())

    def test_bad_candles_fail_instead_of_becoming_trades(self):
        for variant in ('nan','duplicate','bad_ohlc'):
            with self.subTest(variant=variant):
                frame = demo_candles(220)
                if variant == 'nan': frame.loc[219, 'close'] = np.nan
                if variant == 'duplicate': frame.loc[219, 'timestamp'] = frame.loc[218, 'timestamp']
                if variant == 'bad_ohlc': frame.loc[219, 'high'] = 1
                with self.assertRaises(ValueError): validate_candles(frame)

    def test_invalid_configuration_fails_fast(self):
        for kwargs in ({'leverage':0}, {'fee_rate':D('NaN')}, {'slippage':D(-1)}, {'poll_seconds':0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): Settings(**kwargs)

    def test_missing_candle_or_wrong_timeframe_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'gaps or timeframe'):
            SentinelStrategy(Settings()).prepare(demo_candles(250).drop(index=100))
        with self.assertRaisesRegex(ValueError, 'gaps or timeframe'):
            SentinelStrategy(replace(Settings(), timeframe='4h')).prepare(demo_candles(250))


class AsyncFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_candles_cannot_open_a_position(self):
        db = DatabaseManager()
        self.addCleanup(db.close)
        bot = CryptoSentinelBot(Settings(), db)
        frame = demo_candles(300)
        bot.client.get_ohlcv = AsyncMock(return_value=frame)
        bot.client.get_current_price = AsyncMock(return_value=D(30000))
        last = frame.iloc[-1]['timestamp'] + pd.Timedelta(days=1)
        bot.client.now_ms = lambda: int(last.timestamp()*1000)
        self.assertEqual(await bot.analyze_once(), 0)
        self.assertEqual(db.trades(), [])
        bot.client.get_current_price.assert_not_awaited()

    async def test_diagnostic_cleans_up_client_and_does_not_submit_orders(self):
        db = DatabaseManager()
        self.addCleanup(db.close)
        bot = CryptoSentinelBot(Settings(), db)
        bot.client = AsyncMock()
        bot.analyze_once = AsyncMock(return_value=3)
        bot.check_stream = AsyncMock(return_value=True)
        result = await bot.run(check=True)
        self.assertIn('1000.00', result)
        bot.analyze_once.assert_awaited_once_with(trade=False)
        bot.client.__aexit__.assert_awaited_once()
        self.assertEqual(db.trades(), [])

    async def test_combined_messages_reject_stale_out_of_order_and_unknown_symbols(self):
        client = AsyncMock()
        client.now_ms = lambda: 100000
        received = AsyncMock()
        stream = StreamManager(Settings(), client, received)
        self.assertIn('/stream?streams=btcusdt@trade/ethusdt@trade/bnbusdt@trade', stream.socket_url)
        def payload(symbol='BTCUSDT', event=99000):
            return json.dumps({'stream':'btcusdt@trade','data':{'e':'trade','s':symbol,'p':'50000','E':event}})
        self.assertTrue(await stream.handle_message(payload()))
        self.assertTrue(stream.fresh('BTC/USDT'))
        self.assertFalse(await stream.handle_message(payload(event=98000)))
        self.assertFalse(await stream.handle_message(payload(event=1)))
        self.assertFalse(await stream.handle_message(payload(symbol='UNKNOWN')))
        received.assert_awaited_once_with('BTC/USDT', D(50000))

    async def test_client_filters_incomplete_candle_using_exchange_time(self):
        client = BinanceClient(Settings())
        base = 1767225600000
        rows = [[base, '100','101','99','100','20',base+3599999],
                [base+3600000,'100','101','99','100','20',base+7199999]]
        client._get = AsyncMock(side_effect=[rows, {'serverTime':base+3605000}])
        result = await client.get_ohlcv('BTC/USDT')
        self.assertEqual(len(result), 1)

    async def test_async_entrypoint_really_awaits_run(self):
        with patch('app.trading.bot.CryptoSentinelBot') as cls:
            cls.return_value.run = AsyncMock(return_value='OK')
            from main import main
            # main owns an event loop; execute its synchronous CLI in a thread.
            code = await asyncio.to_thread(main, ['--once','--db',':memory:'])
            self.assertEqual(code, 0)
            cls.return_value.run.assert_awaited_once_with(once=True)

    async def test_bot_analyzes_three_symbols_without_network_or_duplicate_entries(self):
        settings = Settings()
        db = DatabaseManager()
        self.addCleanup(db.close)
        bot = CryptoSentinelBot(settings, db)
        frame = demo_candles(300)
        bot.client.get_ohlcv = AsyncMock(return_value=frame)
        bot.client.get_current_price = AsyncMock(return_value=D(str(frame.iloc[-1]['close'])))
        last = frame.iloc[-1]['timestamp'] + pd.Timedelta(hours=1, seconds=2)
        bot.client.now_ms = lambda: int(last.timestamp()*1000)
        self.assertEqual(await bot.analyze_once(), 3)
        count = len(db.trades())
        self.assertEqual(await bot.analyze_once(), 3)
        self.assertEqual(len(db.trades()), count)


if __name__ == '__main__':
    unittest.main()
