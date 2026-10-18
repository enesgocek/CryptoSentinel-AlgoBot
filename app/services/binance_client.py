"""Public market data only. This client has no authenticated order methods."""
import asyncio
from decimal import Decimal
import time

import aiohttp
import pandas as pd

from app.analysis.strategy import validate_candles
from app.core.models import decimal


class MarketDataError(RuntimeError):
    pass


class BinanceClient:
    def __init__(self, settings):
        self.settings = settings
        self.session = None
        self.clock_offset = 0
        self.pause_until = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(
            total=self.settings.request_timeout), trust_env=True)
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def _get(self, path, params=None):
        if self.session is None:
            raise RuntimeError('Use BinanceClient as an async context manager.')
        if time.monotonic() < self.pause_until:
            raise MarketDataError('Binance rate-limit cooldown active.')
        for attempt in range(3):
            try:
                async with self.session.get(self.settings.api_base + path, params=params) as response:
                    if response.status in (418, 429):
                        # Do not retry into an exchange ban; the caller pauses trading.
                        self.pause_until = time.monotonic() + max(60, float(response.headers.get('Retry-After', 60)))
                        raise MarketDataError(f'Binance rate limit ({response.status}); retry later.')
                    if response.status != 200:
                        raise MarketDataError(f'Binance market data HTTP {response.status}.')
                    return await response.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == 2:
                    raise MarketDataError('Binance public data unavailable (network/timeout).') from exc
                await asyncio.sleep(2 ** attempt)

    async def server_time(self):
        payload = await self._get('/api/v3/time')
        server = int(payload['serverTime'])
        self.clock_offset = server - int(time.time() * 1000)
        return server

    def now_ms(self):
        return int(time.time() * 1000) + self.clock_offset

    async def get_ohlcv(self, symbol, limit=1000):
        payload = await self._get('/api/v3/klines', {
            'symbol': symbol.replace('/', ''), 'interval': self.settings.timeframe, 'limit': limit})
        now = await self.server_time()
        rows = [{'timestamp': pd.to_datetime(r[0], unit='ms', utc=True),
                 'open': r[1], 'high': r[2], 'low': r[3], 'close': r[4], 'volume': r[5],
                 'close_time': int(r[6])} for r in payload if int(r[6]) < now]
        if not rows:
            raise MarketDataError('No completed candles returned.')
        return validate_candles(pd.DataFrame(rows))

    async def get_current_price(self, symbol):
        payload = await self._get('/api/v3/ticker/price', {'symbol': symbol.replace('/', '')})
        price = decimal(payload['price'])
        if price <= Decimal(0):
            raise MarketDataError('Non-positive market price.')
        return price
