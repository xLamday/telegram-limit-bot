"""
Utility per la gestione dei permessi Telegram.
"""

from loggerinfo import LoggerInfo
import time
from config.settings import CFG

from telethon import TelegramClient
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import EditAdminRequest, GetParticipantRequest
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChatAdminRights,
    ChatBannedRights,
)

logger = LoggerInfo("antispam.utils.permissions").get_logger()


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

    if event.is_private:
        return

    sender_id = event.sender_id
    chat_id = event.chat_id

    # Caso anonimo: sender_id è None OPPURE uguale al chat_id
    logger.debug(f"[AUTH] sender_id={sender_id} | chat_id={chat_id} | admin_id={CFG.admin_id}")


    if sender_id in CFG.admin_id:
        logger.debug("[AUTH] ✅ Match diretto sender_id == admin_id")
        return True

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

async def imposta_anonimo(client: TelegramClient, chat) -> bool:
    """
    Imposta l'userbot come admin anonimo nel gruppo, nascondendo il nome
    reale dietro al titolo del gruppo nelle azioni visibili agli altri membri.

    Richiede che l'account sia già admin nel gruppo.
    Ritorna True se l'operazione è riuscita, False altrimenti.
    """
    try:
        me = await client.get_me()
        await client(EditAdminRequest(
            channel=chat,
            user_id=me.id,
            admin_rights=ChatAdminRights(
                change_info=True,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=False,
                anonymous=True,
                manage_call=False,
                other=True,
            ),
            rank="Admin",
        ))
        logger.info(f"Userbot impostato come anonimo in {chat.id}.")
        return True
    except Exception as e:
        logger.warning(f"Impossibile impostare anonimato in {chat.id}: {e}")
        return False
