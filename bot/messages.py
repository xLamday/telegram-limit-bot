"""
Handler dei messaggi in entrata — muta automaticamente gli utenti non autorizzati.
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from telethon import TelegramClient, events

from config.settings import CFG
from db import db
from utils.permissions import is_admin, is_authorized_admin  # ← aggiunto
from bot.mute_queue import MuteQueue, MuteTask

logger = logging.getLogger("antispam.messages")

# Deduplicazione: (group_id, user_id) → timestamp ultimo evento processato
_last_event: dict = defaultdict(float)


def register_message_handler(client: TelegramClient, mute_queue: MuteQueue, me_id: int):

    @client.on(events.NewMessage)
    async def on_message(event):
        # Ignora messaggi privati, dell'admin e del bot stesso
        if event.is_private:
            return
        if await is_authorized_admin(event, client) or event.sender_id == me_id:
            return

        chat = await event.get_chat()
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
            db.set_user(chat.id, user.id, "limited")
            status = "limited"

        if status == "free":
            return

        # Utente limited → accoda mute
        logger.info(f"Messaggio da utente limited {user.id} in gruppo {chat.id} — accodato mute.")
        await mute_queue.enqueue(MuteTask(chat, user.id, chat.id, event))
