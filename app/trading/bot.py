"""Async live-data paper bot; every exchange interaction is public/read-only."""
import asyncio
from datetime import datetime, timezone
import logging
import time

import pandas as pd

from app.analysis.strategy import SentinelStrategy
from app.core.database import DatabaseManager
from app.services.binance_client import BinanceClient, MarketDataError
from app.services.reporting import format_report
from app.services.telegram_bot import TelegramBot
from app.trading.paper_engine import PaperEngine
from app.trading.stream_manager import StreamManager

log = logging.getLogger(__name__)


class CryptoSentinelBot:
    def __init__(self, settings, db=None):
        self.settings = settings
        self.db = db or DatabaseManager(settings.db_path, settings.initial_capital)
        self.owns_db = db is None
        self.strategy = SentinelStrategy(settings)
        self.engine = PaperEngine(self.db, settings)
        self.client = BinanceClient(settings)
        self.notifier = TelegramBot(settings)
        self.streamer = StreamManager(settings, self.client, self.on_price)
        self.prices = {}
        self.last_evaluated = {}
        self.price_health = {}
        self.notifications = asyncio.Queue(maxsize=200)
        unexpected = {t['symbol'] for t in self.db.active_trades()} - set(settings.symbols)
        if unexpected:
            if self.owns_db:
                self.db.close()
            raise ValueError(f'Open positions are outside SYMBOLS: {sorted(unexpected)}. Restore those symbols.')

    async def on_price(self, symbol, price):
        self.prices[symbol] = price
        self.price_health[symbol] = time.monotonic()
        fills = self.engine.on_price(symbol, price)
        for fill in fills:
            log.info('%s %s | net PnL %+.4f USDT', symbol, fill.reason, fill.net_pnl)
            if self.settings.telegram_enabled:
                try:
                    self.notifications.put_nowait(f'SANAL {symbol} #{fill.trade_id}: {fill.reason}; net PnL {fill.net_pnl:+.4f} USDT')
                except asyncio.QueueFull:
                    log.warning('Notification queue full; fill remains safely stored in the ledger.')
        return fills

    async def notification_loop(self):
        while True:
            message = await self.notifications.get()
            try:
                await self.notifier.send_message(message)
            finally:
                self.notifications.task_done()

    async def check_stream(self):
        task = asyncio.create_task(self.streamer.run())
        try:
            async def wait_for_symbols():
                while not all(self.streamer.fresh(s) for s in self.settings.symbols):
                    await asyncio.sleep(.1)
            await asyncio.wait_for(wait_for_symbols(), timeout=15)
            log.info('WebSocket verified: fresh trade events received for all %s symbols.', len(self.settings.symbols))
            return True
        except asyncio.TimeoutError:
            log.warning('WebSocket check timed out; public REST data passed and remains the fallback.')
            return False
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def analyze_once(self, trade=True):
        successes = 0
        for symbol in self.settings.symbols:
            try:
                frame = await self.client.get_ohlcv(symbol)
                # A successful HTTP response with old candles is not a healthy feed.
                interval = pd.Timedelta(self.settings.timeframe)
                latest = pd.Timestamp(frame.iloc[-1]['timestamp'])
                now = pd.to_datetime(self.client.now_ms(), unit='ms', utc=True)
                if now - latest > interval * 2 + pd.Timedelta(seconds=self.settings.stale_seconds):
                    raise MarketDataError('Candle feed is stale; new entries suspended.')
                price = await self.client.get_current_price(symbol)
                await self.on_price(symbol, price)
                successes += 1
                candle_key = latest.isoformat()
                if self.last_evaluated.get(symbol) == candle_key:
                    continue
                evaluation = await asyncio.to_thread(self.strategy.evaluate, frame, symbol)
                if evaluation:
                    self.last_evaluated[symbol] = candle_key
                    log.info('%s | closed candle %s | score %s | price %s', symbol,
                             evaluation.candle, evaluation.score, price)
                    if trade:
                        if time.monotonic() - self.price_health.get(symbol, float('-inf')) >= self.settings.stale_seconds:
                            log.warning('%s: quote expired during analysis; entry skipped.', symbol)
                            continue
                        trade_id = self.engine.submit(evaluation, price)
                        if trade_id:
                            log.info('PAPER position #%s opened: %s %s', trade_id, symbol, evaluation.plan.side)
                            await self.notifier.send_message(f'SANAL ISLEM #{trade_id}: {symbol} {evaluation.plan.side}')
            except (MarketDataError, ValueError, KeyError, TypeError) as exc:
                log.warning('%s: %s', symbol, exc)
        return successes

    async def monitor_prices(self):
        while True:
            for symbol in self.settings.symbols:
                if self.streamer.fresh(symbol):
                    continue
                try:
                    await self.on_price(symbol, await self.client.get_current_price(symbol))
                except MarketDataError:
                    if time.monotonic() - self.price_health.get(symbol, float('-inf')) > self.settings.stale_seconds:
                        log.warning('%s: no fresh prices; no new orders will use cached prices.', symbol)
            await asyncio.sleep(self.settings.price_poll_seconds)

    async def market_loop(self):
        while True:
            await self.analyze_once()
            await asyncio.sleep(self.settings.poll_seconds)

    async def report_loop(self):
        last_day = None
        while True:
            day = datetime.now(timezone.utc).date()
            if day != last_day:
                report = format_report(self.db, self.prices)
                log.info('\n%s', report)
                await self.notifier.send_message(report)
                last_day = day
            await asyncio.sleep(30)

    async def run(self, once=False, check=False):
        try:
            async with self.client:
                log.info('PAPER mode | public Binance prices | local database: %s', self.db.path)
                ok = await self.analyze_once(trade=not check)
                if once or check:
                    if ok != len(self.settings.symbols):
                        raise MarketDataError('Not all symbols passed the live-data check.')
                    if check:
                        await self.check_stream()
                    return format_report(self.db, self.prices)
                tasks = [asyncio.create_task(coro) for coro in (
                    self.streamer.run(), self.monitor_prices(), self.market_loop(),
                    self.report_loop(), self.notification_loop())]
                try:
                    await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            if self.owns_db:
                self.db.close()
