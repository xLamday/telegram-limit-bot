"""
Utility per la gestione dei permessi Telegram.
"""

import logging
import time

from telethon import TelegramClient
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import EditAdminRequest, GetParticipantRequest
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChatAdminRights,
    ChatBannedRights,
)

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


async def set_anonymous(client: TelegramClient, chat) -> bool:
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
            rank="Bot",
        ))
        logger.info(f"Userbot impostato come anonimo in {chat.id}.")
        return True
    except Exception as e:
        logger.warning(f"Impossibile impostare anonimato in {chat.id}: {e}")
        return False
