import logging

from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application

from .messages.alerts import Signal, log_r2_text, heartbeat_text, error_text
from .routers import main_router
from .state import BotState, STATE_KEY

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token: str, chat_ids: str):
        self.chat_ids = [int(x.strip()) for x in str(chat_ids).split(",") if x.strip()]
        self._state = BotState()
        self.app = Application.builder().token(token).build()
        self.app.bot_data[STATE_KEY] = self._state
        main_router.setup(self.app)

    @property
    def enabled_r2(self) -> bool:
        return self._state.enabled_r2

    @property
    def enabled_r3(self) -> bool:
        return self._state.enabled_r3

    @property
    def enabled_r4(self) -> bool:
        return self._state.enabled_r4

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

    # ------------------------------------------------------------------
    # Internal sender
    # ------------------------------------------------------------------

    async def _send(self, text: str) -> None:
        for chat_id in self.chat_ids:
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError as e:
                logger.error("Telegram send failed for %s: %s", chat_id, e)

    # ------------------------------------------------------------------
    # Signal sender (all rules)
    # ------------------------------------------------------------------

    async def send_signal(self, signal: Signal) -> None:
        await self._send(signal.render())

    async def send_log_r2(self, market_title: str, log_data: dict) -> None:
        await self._send(log_r2_text(market_title, log_data))

    # ------------------------------------------------------------------
    # Shared senders
    # ------------------------------------------------------------------

    async def send_heartbeat(self, match_count: int, kalshi_matches: list[str] | None = None) -> None:
        await self._send(heartbeat_text(
            match_count,
            self._state.enabled_r2, self._state.enabled_r3, self._state.enabled_r4,
            kalshi_matches=kalshi_matches,
        ))

    async def send_error(self, message: str) -> None:
        await self._send(error_text(message))
