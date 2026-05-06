import logging

from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application

from .messages import alerts
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
    def enabled(self) -> bool:
        return self._state.enabled

    @property
    def enabled_r2(self) -> bool:
        return self._state.enabled_r2

    @property
    def enabled_r3(self) -> bool:
        return self._state.enabled_r3

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
    # Rule 1 alert senders
    # ------------------------------------------------------------------

    async def send_entry(
        self, player: str, match: str, score: str, price: float,
        detail: str = "", spread: float | None = None,
    ) -> None:
        await self._send(alerts.entry_text(player, match, score, price, detail, spread=spread))

    async def send_exit(
        self, player: str, match: str, score: str,
        exit_price: float | None = None,
        stats: dict | None = None,
        exit_reason: str | None = None,
    ) -> None:
        await self._send(alerts.exit_text(player, match, score,
                                          exit_price=exit_price, stats=stats,
                                          exit_reason=exit_reason))

    async def send_reentry(
        self, player: str, match: str, score: str, price: float,
        detail: str = "", spread: float | None = None,
    ) -> None:
        await self._send(alerts.reentry_text(player, match, score, price, detail, spread=spread))

    async def send_log(self, player: str, match: str, log_data: dict) -> None:
        await self._send(alerts.log_text(player, match, log_data))

    # ------------------------------------------------------------------
    # Rule 2 alert senders
    # ------------------------------------------------------------------

    async def send_entry_r2(self, title: str, price: float, prev_price: float, reentry: bool = False) -> None:
        await self._send(alerts.entry_r2_text(title, price, prev_price, reentry=reentry))

    async def send_exit_r2(self, title: str, exit_price: float, entry_price: float | None, reason: str) -> None:
        await self._send(alerts.exit_r2_text(title, exit_price, entry_price, reason))

    # ------------------------------------------------------------------
    # Rule 3 alert senders
    # ------------------------------------------------------------------

    async def send_entry_r3(
        self, player: str, match: str, price: float, prev_price: float,
        set1_score: str, reentry: bool = False,
    ) -> None:
        await self._send(alerts.entry_r3_text(player, match, price, prev_price, set1_score, reentry=reentry))

    async def send_exit_r3(
        self, player: str, match: str, exit_price: float,
        entry_price: float | None, reason: str,
    ) -> None:
        await self._send(alerts.exit_r3_text(player, match, exit_price, entry_price, reason))

    # ------------------------------------------------------------------
    # Shared senders
    # ------------------------------------------------------------------

    async def send_heartbeat(self, match_count: int, kalshi_count: int = 0, tradeable_names: list | None = None) -> None:
        await self._send(alerts.heartbeat_text(
            match_count, kalshi_count,
            self._state.enabled, self._state.enabled_r2, self._state.enabled_r3,
            tradeable_names or [],
        ))

    async def send_error(self, message: str) -> None:
        await self._send(alerts.error_text(message))
