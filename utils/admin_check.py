"""
Verifica che il bot (userbot) sia admin in tutti i gruppi registrati.

- Controlla solo i gruppi nel DB (ignora gli altri)
- Se non è admin in un gruppo registrato → notifica in chat privata con l'admin
- Può essere chiamato all'avvio e/o schedulato periodicamente
"""

import logging
from typing import Optional

from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError, ChannelPrivateError, FloodWaitError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChannelParticipantSelf,
)

from config.settings import CFG
from db import db

logger = logging.getLogger("antispam.admin_check")


async def check_admin_in_registered_groups(client: TelegramClient) -> list[int]:
    """
    Controlla se il bot è admin in ogni gruppo registrato nel DB.

    Ritorna la lista dei group_id in cui NON è admin.
    Invia una notifica privata all'admin per ogni gruppo problematico.
    """
    groups = db.list_groups()
    if not groups:
        logger.info("Nessun gruppo registrato — check admin saltato.")
        return []

    me = await client.get_me()
    problems: list[int] = []

    for group in groups:
        group_id = group["group_id"]
        group_name = group["group_name"]

        is_ok = await _check_single_group(client, me.id, group_id, group_name)
        if not is_ok:
            problems.append(group_id)
            await _notify_admin(client, group_id, group_name)

    if problems:
        logger.warning(f"⚠️ Non sono admin in {len(problems)} gruppo/i: {problems}")
    else:
        logger.info(f"✅ Admin check OK su {len(groups)} gruppo/i registrati.")

    return problems


async def _check_single_group(
    client: TelegramClient, me_id: int, group_id: int, group_name: str
) -> bool:
    """
    Ritorna True se il bot è admin nel gruppo, False altrimenti.
    In caso di errore di accesso ritorna False (gruppo inaccessibile = problema).
    """
    try:
        p = await client(GetParticipantRequest(group_id, me_id))
        participant = p.participant

        if isinstance(participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
            logger.debug(f"✅ Admin in '{group_name}' ({group_id})")
            return True

        # Siamo nel gruppo ma non admin
        logger.warning(f"❌ Non admin in '{group_name}' ({group_id}) — status: {type(participant).__name__}")
        return False

    except ChatAdminRequiredError:
        logger.warning(f"❌ ChatAdminRequiredError in '{group_name}' ({group_id})")
        return False
    except ChannelPrivateError:
        logger.warning(f"❌ Gruppo privato inaccessibile '{group_name}' ({group_id})")
        return False
    except FloodWaitError as e:
        logger.warning(f"⏳ FloodWait {e.seconds}s durante check di '{group_name}'")
        import asyncio
        await asyncio.sleep(e.seconds + 2)
        return await _check_single_group(client, me_id, group_id, group_name)
    except Exception as e:
        logger.warning(f"❌ Errore check admin '{group_name}' ({group_id}): {e}")
        return False


async def _notify_admin(client: TelegramClient, group_id: int, group_name: str):
    """Invia un messaggio privato all'admin segnalando il problema."""
    try:
        await client.send_message(
            CFG.admin_id,
            f"⚠️ <b>Attenzione</b>\n\n"
            f"Non sono admin nel gruppo registrato:\n"
            f"• <b>{group_name}</b> (<code>{group_id}</code>)\n\n"
            f"Non potrò mutare nuovi utenti in questo gruppo finché "
            f"non mi vengono assegnati i permessi di admin.",
            parse_mode="html",
        )
        logger.info(f"Notifica admin inviata per gruppo {group_id}.")
    except Exception as e:
        logger.error(f"Impossibile notificare admin per gruppo {group_id}: {e}")
