"""
Handlers dei comandi admin del bot.
"""


from loggerinfo import LoggerInfo
import time

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.types import ChannelParticipantsAdmins as _ChannelParticipantsAdmins
import asyncio

from config.settings import CFG
from db import db
from utils.permissions import imposta_anonimo, is_authorized_admin
from bot.mute_queue import MuteQueue, MuteTask


logger = LoggerInfo("antispam.commands").get_logger()


def register_commands(client: TelegramClient, mute_queue: MuteQueue):

    # ── /registragruppo ────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/registragruppo"))
    async def cmd_registragruppo(event):

        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
           logger.info(f"L'utente {event.sender.first_name}, ha provato a usare il comando.")
           return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()

        if db.group_exists(chat.id):
            await event.reply("❌ Gruppo già registrato nel database.")
            return False

        
        # Imposta l'userbot come anonimo nel gruppo
        await imposta_anonimo(client, chat)            
        
        db.upsert_group(chat.id, chat.title)

        await event.reply(
            f"⏳ Registrazione <b>{chat.title}</b> in corso…\n"
            f"Sto raccogliendo la lista degli admin.",
            parse_mode="html",
        )

        # ── FASE 1: raccogli tutti gli admin con una sola chiamata filtrata ──
        # iter_participants con filter=admins usa l'endpoint channels.getParticipants
        # con flag ADMINS → una sola richiesta, nessuna chiamata per-utente.
        admin_ids: set[int] = set()
        async for admin in client.iter_participants(
            chat, filter=_ChannelParticipantsAdmins()
        ):
            if admin.bot:
                continue
            admin_ids.add(admin.id)
            logger.debug(f"Admin trovato: {admin.id} ({getattr(admin, 'first_name', '?')})")

        await event.reply(
            f"✅ Registrazione del canale <b>{chat.title}</b> completata\n"
            f"Admin raccolti, inizio a salvare gli admin nel database.",
            parse_mode="html",
        )

        # Salva tutti gli admin nel DB in una transazione unica
        if admin_ids:
            db.bulk_set_admins(chat.id, list(admin_ids))
        logger.info(f"Gruppo {chat.id}: {len(admin_ids)} admin registrati.")

        
        await event.reply(
            f"✅ Raccolta admin <b>{chat.title}</b> completata\n"
            f"Admin registrati nel database, procedo con il mute.",
            parse_mode="html",
        )

        # ── FASE 2: itera TUTTI i membri e muta chi non è admin ──
        muted_count = 0
        async for user in client.iter_participants(chat):
            if user.bot:
                continue
            if user.id in admin_ids:
                continue  # skip admin — non toccarli
            existing = db.get_user_status(chat.id, user.id)
            if existing in ("free", "admin"):
                continue  # già esenti
            db.set_user(chat.id, user.id, "limited")
            await mute_queue.enqueue(MuteTask(chat, user.id, chat.id))
            muted_count += 1

        await event.reply(
            f"✅ Gruppo <b>{chat.title}</b> registrato.\n"
            f"🛡 {len(admin_ids)} admin esentati.\n"
            f"🔇 {muted_count} utenti accodati per mute (72h).",
            parse_mode="html",
        )
        logger.info(f"Gruppo {chat.id}, {chat.title}: {muted_count} utenti accodati per mute.")

    # ── /limita ────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/limita (.+)"))
    async def cmd_limita(event):

        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
           return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        target = event.pattern_match.group(1).strip()
        try:
            user = await client.get_entity(target)
            db.set_user(chat.id, user.id, "limited")
            await mute_queue.enqueue(MuteTask(chat, user.id, chat.id))
            await event.reply(f"🔇 {user.first_name} limitato per {CFG.mute_hours} ore.")
        except Exception as e:
            await event.reply(f"⚠️ Errore: {e}")

    # ── /free ──────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/free (.+)"))
    async def cmd_free(event):
        if not await is_authorized_admin(event, client):
           return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        target = event.pattern_match.group(1).strip()
        try:
            user = await client.get_entity(target)
            db.set_user(chat.id, user.id, "free")
            await client.edit_permissions(chat, user.id, send_messages=True)
            await event.reply(f"✅ {user.first_name} liberato permanentemente.")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await event.reply("⚠️ Rate limit Telegram: riprova tra qualche secondo.")
        except Exception as e:
            await event.reply(f"⚠️ Errore: {e}")

    # ── /log ───────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/log"))
    async def cmd_log(event):


        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
           return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        rows = db.list_users(chat.id)
        if not rows:
            return await event.reply("Nessun utente registrato per questo gruppo.")

        lines = ["📋 <b>Log utenti:</b>"]
        for row in rows:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(row["updated_at"]))
            lines.append(f"  <code>{row['user_id']}</code> → {row['status']} ({ts})")

        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n… (troncato)"
        await event.reply(msg, parse_mode="html")

    # ── /gruppi ────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/gruppi"))
    async def cmd_gruppi(event):

        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
           return await event.reply("❌ Non sei autorizzato.")

        groups = db.list_groups()
        if not groups:
            return await event.reply("Nessun gruppo registrato.")

        lines = ["🗂 <b>Gruppi registrati:</b>"]
        for g in groups:
            ts = time.strftime("%Y-%m-%d", time.localtime(g["registered_at"]))
            lines.append(f"  <code>{g['group_id']}</code> — {g['group_name']} (dal {ts})")
        await event.reply("\n".join(lines), parse_mode="html")
