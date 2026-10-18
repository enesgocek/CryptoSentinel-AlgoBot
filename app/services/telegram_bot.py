"""Optional asynchronous notifications. Disabled unless explicitly configured."""
import asyncio
import logging
import aiohttp

log = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, settings):
        self.settings = settings

    async def send_message(self, message):
        if not self.settings.telegram_enabled:
            return False
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), trust_env=True) as session:
                async with session.post(
                    f'https://api.telegram.org/bot{self.settings.telegram_token}/sendMessage',
                    json={'chat_id': self.settings.telegram_chat_id, 'text': message}) as response:
                    if response.status == 200:
                        return True
                    log.warning('Telegram notification failed (HTTP %s).', response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            # Never log the request URL: it contains the secret token.
            log.warning('Telegram notification unavailable.')
        return False
