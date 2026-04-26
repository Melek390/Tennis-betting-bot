import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application

from .messages import alerts
from .routers import main_router
from .state import BotState, STATE_KEY

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token: str, chat_ids: str):
        # Accepts "id1,id2" or a single id
        self.chat_ids = [int(x.strip()) for x in str(chat_ids).split(",") if x.strip()]
        self._state = BotState()
        self.app = Application.builder().token(token).build()
        self.app.bot_data[STATE_KEY] = self._state
        main_router.setup(self.app)

    @property
    def enabled_rules(self) -> dict[int, bool]:
        return self._state.enabled_rules

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

    async def _send(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        for chat_id in self.chat_ids:
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            except TelegramError as e:
                logger.error("Telegram send failed for %s: %s", chat_id, e)

    # ------------------------------------------------------------------
    # Alert senders — match_id + player_side encode the state key so
    # the user's button press can call the right StateManager method.
    # ------------------------------------------------------------------

    async def send_entry(
        self, rule: int, player: str, match: str, score: str, price: float,
        match_id: str, player_side: str, detail: str = "",
    ) -> None:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Confirmed entry",   callback_data=f"ce:{match_id}:{player_side}:{rule}"),
            InlineKeyboardButton("I'm skipping this", callback_data=f"se:{match_id}:{player_side}:{rule}"),
        ]])
        await self._send(alerts.entry_text(rule, player, match, score, price, detail), reply_markup=kb)

    async def send_exit(
        self, rule: int, player: str, match: str, score: str,
        match_id: str, player_side: str,
    ) -> None:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Confirmed exit",       callback_data=f"cx:{match_id}:{player_side}:{rule}"),
            InlineKeyboardButton("Keeping my position",  callback_data=f"kx:{match_id}:{player_side}:{rule}"),
        ]])
        await self._send(alerts.exit_text(rule, player, match, score), reply_markup=kb)

    async def send_reentry(
        self, rule: int, player: str, match: str, score: str, price: float,
        match_id: str, player_side: str, detail: str = "",
    ) -> None:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Confirmed re-entry",   callback_data=f"cr:{match_id}:{player_side}:{rule}"),
            InlineKeyboardButton("I'm skipping this",    callback_data=f"sr:{match_id}:{player_side}:{rule}"),
        ]])
        await self._send(alerts.reentry_text(rule, player, match, score, price, detail), reply_markup=kb)

    async def send_heartbeat(self, match_count: int) -> None:
        await self._send(alerts.heartbeat_text(match_count, self._state.enabled_rules))

    async def send_error(self, message: str) -> None:
        await self._send(alerts.error_text(message))
