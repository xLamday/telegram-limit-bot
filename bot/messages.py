"""
Handler dei messaggi in entrata — muta automaticamente gli utenti non autorizzati.
"""

from __future__ import annotations

from loggerinfo import LoggerInfo
import time
from collections import defaultdict

from telethon import TelegramClient, events

from config.settings import CFG
from db import db
from utils.permissions import is_admin, is_authorized_admin
from bot.mute_queue import MuteQueue, MuteTask

logger = LoggerInfo("antispam.bot.messages").get_logger()

# Deduplicazione: (group_id, user_id) → timestamp ultimo evento processato
_last_event: dict[tuple[int, int], float] = defaultdict(float)


def register_message_handler(client: TelegramClient, mute_queue: MuteQueue, me_id: int):
    """Registra l'handler globale dei messaggi per applicare auto-mute nei gruppi registrati."""

    @client.on(events.NewMessage)
    async def on_message(event):
        # Ignora messaggi privati, dell'admin e del bot stesso
        if event.is_private:
            return

        chat = await event.get_chat()

        # Ignora completamente i gruppi NON registrati nel DB.
        # Il bot opera solo dove è stato esplicitamente attivato con /registragruppo.
        if not db.group_exists(chat.id):
            return


        if await is_authorized_admin(event, client) or event.sender_id == me_id:
            return

        user = await event.get_sender()
        if user is None:
            return

        # Deduplicazione: evita di accodare N mute per la stessa persona
        # se manda più messaggi in rapida successione
        dedup_key = (chat.id, user.id)
        now = time.monotonic()
        if now - _last_event[dedup_key] < CFG.dedup_window:
            return
        _last_event[dedup_key] = now

        # Ignora completamente i gruppi NON registrati nel DB.
        # Il bot opera solo dove è stato esplicitamente attivato con /registragruppo.
        if not db.group_exists(chat.id):
            return

        # Salta se è admin
        if await is_admin(client, chat, user.id):
            return

        # Recupera stato dal DB
        status = db.get_user_status(chat.id, user.id)
        if status is None:
            # Nuovo utente in un gruppo registrato → registra come limited
            from bot.commands import _display_name  # import locale per evitare cicli
            db.set_user(chat.id, user.id, "limited", _display_name(user))
            status = "limited"

        if status in ("free", "admin"):
            return

        # Utente limited → accoda mute
        logger.info(f"Messaggio da utente limited {user.id} in gruppo {chat.id} — accodato mute.")
        await mute_queue.enqueue(MuteTask(chat, user.id, chat.id, event))
