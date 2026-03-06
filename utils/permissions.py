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

async def is_authorized_admin(event, client) -> bool:
    from config.settings import CFG

    sender_id = event.sender_id
    chat_id = event.chat_id

    logger.debug(f"[AUTH] sender_id={sender_id} | chat_id={chat_id} | admin_id={CFG.admin_id}")

    # Caso normale: utente non anonimo
    if sender_id == CFG.admin_id:
        logger.debug("[AUTH] ✅ Match diretto sender_id == admin_id")
        return True

    # Caso anonimo: sender_id è None OPPURE uguale al chat_id
    if sender_id is None or sender_id == chat_id:
        logger.debug("[AUTH] 🎭 Sender anonimo rilevato, verifico se admin_id è admin del gruppo...")
        try:
            p = await client(GetParticipantRequest(chat_id, CFG.admin_id))
            logger.debug(f"[AUTH] Participant trovato: {p.participant}")
            result = isinstance(p.participant, (ChannelParticipantAdmin, ChannelParticipantCreator))
            logger.debug(f"[AUTH] È admin/creator? {result}")
            return result
        except Exception as e:
            logger.debug(f"[AUTH] ❌ Eccezione: {e}")
            return False

    logger.debug(f"[AUTH] ❌ Nessun caso matched")
    return False