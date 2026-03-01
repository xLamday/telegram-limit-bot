"""
Utility per la gestione dei permessi Telegram.
"""

import logging
from telethon import TelegramClient
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator, ChatBannedRights
import time

logger = logging.getLogger("antispam.utils.permissions")


def mute_rights(hours: int) -> ChatBannedRights:
    return ChatBannedRights(
        until_date=int(time.time()) + hours * 3600,
        send_messages=True,
    )


FREE_RIGHTS = ChatBannedRights(until_date=None, send_messages=False)


async def is_admin(client: TelegramClient, chat, user_id: int) -> bool:
    """
    Controlla se un utente è admin o creator del gruppo.
    In caso di errore ritorna True (fail-safe: non mutare in caso di dubbio).
    """
    try:
        p = await client(GetParticipantRequest(chat, user_id))
        return isinstance(p.participant, (ChannelParticipantAdmin, ChannelParticipantCreator))
    except UserNotParticipantError:
        return False
    except Exception as e:
        logger.warning(f"Errore controllo admin per {user_id}: {e}")
        return True  # fail-safe
