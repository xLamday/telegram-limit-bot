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


def _display_name(user) -> str:
    """Restituisce un nickname leggibile a partire da un oggetto User Telethon."""
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    first = getattr(user, "first_name", None) or ""
    last = getattr(user, "last_name", None) or ""
    full = (first + " " + last).strip()
    return full or str(getattr(user, "id", "?"))


def register_commands(client: TelegramClient, mute_queue: MuteQueue):
    """Registra sul client Telethon i comandi admin (/registragruppo, /limita, /free, /aggiungi_admin, /log, /gruppi, /utenti)."""

    # ── /registragruppo ────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/registragruppo"))
    async def cmd_registragruppo(event):

        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
            try:
                sender = await event.get_sender()
                who = getattr(sender, "first_name", None) or str(event.sender_id)
            except Exception:
                who = str(event.sender_id)
            logger.info(f"Utente non autorizzato ha provato /registragruppo: {who}")
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
            db.set_user(chat.id, user.id, "limited", _display_name(user))
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
        raw_target = event.pattern_match.group(1).strip()

        # Supporta sia username che ID numerico
        if raw_target.lstrip("-").isdigit():
            target = int(raw_target)
        else:
            target = raw_target

        try:
            user = await client.get_entity(target)
            db.set_user(chat.id, user.id, "limited", _display_name(user))
            await mute_queue.enqueue(MuteTask(chat, user.id, chat.id))
            await event.reply(f"🔇 {user.first_name} limitato per {CFG.mute_hours} ore.")
        except Exception:
            logger.exception("Errore /limita", extra={"chat_id": chat.id, "target": target})
            await event.reply("⚠️ Errore durante il comando. Controlla i log.")

    # ── /free ──────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/free (.+)"))
    async def cmd_free(event):
        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
            return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        raw_target = event.pattern_match.group(1).strip()

        # Supporta sia username che ID numerico
        if raw_target.lstrip("-").isdigit():
            target = int(raw_target)
        else:
            target = raw_target

        try:
            user = await client.get_entity(target)
            db.set_user(chat.id, user.id, "free", _display_name(user))
            await client.edit_permissions(chat, user.id, send_messages=True)
            await event.reply(f"✅ {user.first_name} liberato permanentemente.")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await event.reply("⚠️ Rate limit Telegram: riprova tra qualche secondo.")
        except Exception:
            logger.exception("Errore /free", extra={"chat_id": chat.id, "target": target})
            await event.reply("⚠️ Errore durante il comando. Controlla i log.")

    # ── /aggiungi_admin ─────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/aggiungi_admin (.+)"))
    async def cmd_aggiungi_admin(event):
        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
            return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        raw_target = event.pattern_match.group(1).strip()

        # Supporta sia username che ID numerico, come /free e /limita
        if raw_target.lstrip("-").isdigit():
            target = int(raw_target)
        else:
            target = raw_target

        try:
            user = await client.get_entity(target)
            db.set_user(chat.id, user.id, "admin", _display_name(user))
            # Rimuove subito il mute (se presente)
            await client.edit_permissions(chat, user.id, send_messages=True)
            await client.edit_admin(chat, user.id, is_admin=True)
            await event.reply(f"✅ {user.first_name} ora è registrato come admin ed è stato smutato.")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await event.reply("⚠️ Rate limit Telegram: riprova tra qualche secondo.")
        except Exception:
            logger.exception("Errore /aggiungi_admin", extra={"chat_id": chat.id, "target": target})
            await event.reply("⚠️ Errore durante il comando. Controlla i log.")

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
            nick = row["username"] or str(row["user_id"])
            lines.append(f"  {nick} — <code>{row['user_id']}</code> → {row['status']} ({ts})")

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

    # ── /utenti ─────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern=r"/utenti"))
    async def cmd_utenti(event):

        if event.is_private:
            return

        if not await is_authorized_admin(event, client):
            return await event.reply("❌ Non sei autorizzato.")

        chat = await event.get_chat()
        rows = db.list_users(chat.id)
        if not rows:
            return await event.reply("Nessun utente registrato per questo gruppo.")

        lines = ["👥 <b>Utenti registrati (non admin):</b>"]
        count = 0
        for row in rows:
            if row["status"] == "admin":
                continue
            nick = row["username"] or str(row["user_id"])
            lines.append(f"• {nick} — <code>{row['user_id']}</code> [{row['status']}]")
            count += 1
            if len("\n".join(lines)) > 3800:
                lines.append("… (lista troncata)")
                break

        if count == 0:
            return await event.reply("Nessun utente non-admin registrato per questo gruppo.")

        await event.reply("\n".join(lines), parse_mode="html")
