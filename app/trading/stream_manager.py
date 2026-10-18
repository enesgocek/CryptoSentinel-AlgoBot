"""Combined trade stream with bounded reconnects and per-symbol freshness."""
import asyncio
import json
import logging
import time

import aiohttp

from app.core.models import decimal

log = logging.getLogger(__name__)


class StreamManager:
    def __init__(self, settings, client, on_price):
        self.settings, self.client, self.on_price = settings, client, on_price
        self.prices = {}
        self.received = {}
        self.event_times = {}
        self.connected = False
        names = '/'.join(s.replace('/', '').lower() + '@trade' for s in settings.symbols)
        self.socket_url = settings.ws_base + '?streams=' + names

    def fresh(self, symbol):
        return time.monotonic() - self.received.get(symbol, float('-inf')) < self.settings.stale_seconds

    @staticmethod
    def parse_message(message):
        payload = json.loads(message)
        data = payload.get('data', payload)
        if not isinstance(data, dict) or data.get('e') != 'trade':
            return None
        price = decimal(data['p'])
        if price <= 0:
            return None
        return data['s'], price, int(data['E'])

    async def handle_message(self, message):
        parsed = self.parse_message(message)
        if parsed is None:
            return False
        raw, price, event_ms = parsed
        symbol = next((s for s in self.settings.symbols if s.replace('/', '') == raw), None)
        age = self.client.now_ms() - event_ms
        if symbol is None or age > self.settings.stale_seconds * 1000 or age < -5000:
            return False
        if event_ms < self.event_times.get(symbol, -1):
            return False
        self.prices[symbol] = price
        self.received[symbol] = time.monotonic()
        self.event_times[symbol] = event_ms
        await self.on_price(symbol, price)
        return True

    async def run(self):
        attempts = 0
        while True:
            try:
                async with self.client.session.ws_connect(self.socket_url, heartbeat=20,
                                                          receive_timeout=self.settings.stale_seconds) as ws:
                    self.connected = True
                    attempts = 0
                    log.info('Binance combined price stream connected.')
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            try:
                                await self.handle_message(message.data)
                            except (ValueError, KeyError, TypeError):
                                log.warning('Invalid price stream message ignored.')
                        elif message.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                            break
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                log.warning('Price stream unavailable; REST monitoring remains active.')
            finally:
                self.connected = False
            attempts += 1
            await asyncio.sleep(min(30, 2 ** min(attempts, 5)))
