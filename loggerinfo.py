"""
loggerinfo.py — Sistema di logging centralizzato per il bot antispam.

Funzionalità:
  - Colori ANSI in console per livello (DEBUG grigio, INFO verde, WARNING giallo,
    ERROR rosso, CRITICAL rosso brillante)
  - File rotante globale  → logs/bot.log       (tutti i livelli)
  - File errori dedicato  → logs/errors.log     (solo WARNING+)
  - File per modulo       → logs/<modulo>.log   (opzionale, opt-in)
  - Livello configurabile via env  LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
  - Zero handler duplicati anche con import multipli
  - Compatibile 1:1 con il vecchio LoggerInfo (stessa interfaccia get_logger())
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


# ── Costanti ────────────────────────────────────────────────────────────────

# Dimensione massima di ogni file di log prima della rotazione (10 MB)
_MAX_BYTES = 10 * 1024 * 1024
# Numero di backup da conservare per ogni file rotante
_BACKUP_COUNT = 7
# Cartella predefinita dei log
_DEFAULT_LOG_DIR = "logs"
# Nome del file di log globale
_GLOBAL_LOG_FILE = "bot.log"
# Nome del file dedicato agli errori
_ERROR_LOG_FILE = "errors.log"


# ── Codici colore ANSI ───────────────────────────────────────────────────────

_RESET  = "\033[0m"
_GREY   = "\033[38;5;245m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_BRED   = "\033[1;31m"   # rosso bold per CRITICAL

_LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG:    _GREY,
    logging.INFO:     _GREEN,
    logging.WARNING:  _YELLOW,
    logging.ERROR:    _RED,
    logging.CRITICAL: _BRED,
}


class _ColorFormatter(logging.Formatter):
    """Formatter che colora il livello e il nome del logger in console."""

    _BASE_FMT = "%(asctime)s  {color}%(levelname)-8s{reset}  \033[1m%(name)s\033[0m  %(message)s"
    _DATE_FMT = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, _RESET)
        fmt = self._BASE_FMT.format(color=color, reset=_RESET)
        formatter = logging.Formatter(fmt=fmt, datefmt=self._DATE_FMT)
        return formatter.format(record)


class _PlainFormatter(logging.Formatter):
    """Formatter senza colori per i file (i codici ANSI sporcherebbero i file)."""

    _FMT  = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    _DATE = "%Y-%m-%d %H:%M:%S"

    def __init__(self):
        super().__init__(fmt=self._FMT, datefmt=self._DATE)


# ── Handler globali (condivisi tra tutti i logger) ───────────────────────────
# Vengono creati una sola volta al primo import, poi riusati.
# Questo evita che ogni LoggerInfo() aggiunga handler duplicati al root.

_handlers_initialized = False
_global_file_handler:  Optional[RotatingFileHandler] = None
_error_file_handler:   Optional[RotatingFileHandler] = None
_console_handler:      Optional[logging.StreamHandler] = None


def _init_global_handlers(log_dir: str = _DEFAULT_LOG_DIR) -> None:
    """Inizializza gli handler globali (idempotente: chiamabile N volte)."""
    global _handlers_initialized, _global_file_handler, _error_file_handler, _console_handler

    if _handlers_initialized:
        return

    os.makedirs(log_dir, exist_ok=True)
    plain = _PlainFormatter()

    # Handler file globale — tutti i livelli
    _global_file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, _GLOBAL_LOG_FILE),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    _global_file_handler.setLevel(logging.DEBUG)
    _global_file_handler.setFormatter(plain)

    # Handler file errori — solo WARNING+
    _error_file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, _ERROR_LOG_FILE),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    _error_file_handler.setLevel(logging.WARNING)
    _error_file_handler.setFormatter(plain)

    # Handler console — colorato
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.DEBUG)
    _console_handler.setFormatter(_ColorFormatter())

    _handlers_initialized = True


def _resolve_level() -> int:
    """
    Legge LOG_LEVEL dall'ambiente.
    Valori accettati (case-insensitive): DEBUG, INFO, WARNING, ERROR, CRITICAL.
    Default: DEBUG.
    """
    raw = os.getenv("LOG_LEVEL", "DEBUG").upper().strip()
    level = getattr(logging, raw, None)
    if not isinstance(level, int):
        level = logging.DEBUG
    return level


# ── Classe pubblica ──────────────────────────────────────────────────────────

class LoggerInfo:
    """
    Factory per logger applicativi.

    Utilizzo:
        logger = LoggerInfo("antispam.commands").get_logger()
        logger.info("Comando eseguito")

    Parametri:
        name          Nome del logger (usato come prefisso nei log).
                      Convenzione: "antispam.<modulo>", es. "antispam.DB".
        log_dir       Cartella dove scrivere i log (default: "logs/").
        log_file      Se fornito, crea un file di log dedicato SOLO per questo
                      modulo in aggiunta ai file globali.
                      Se None (default), scrive solo su bot.log ed errors.log.
        level         Livello minimo del logger. Se None legge LOG_LEVEL dall'env.

    File prodotti:
        logs/bot.log        — tutto il traffico (tutti i moduli)
        logs/errors.log     — solo WARNING / ERROR / CRITICAL (tutti i moduli)
        logs/<log_file>     — log del singolo modulo (solo se log_file è fornito)
    """

    def __init__(
        self,
        name: str = __name__,
        log_dir: str = _DEFAULT_LOG_DIR,
        log_file: Optional[str] = None,   # None = nessun file per modulo
        level: Optional[int] = None,
    ):
        # Inizializza handler globali (no-op se già fatto)
        _init_global_handlers(log_dir)

        effective_level = level if level is not None else _resolve_level()

        self.logger = logging.getLogger(name)

        # Imposta il livello solo se il logger non era già configurato
        if self.logger.level == logging.NOTSET:
            self.logger.setLevel(effective_level)

        self.logger.propagate = False  # evita duplicazione verso il root logger

        # Aggiungi gli handler globali (solo se non già presenti)
        existing_handler_types = {type(h) for h in self.logger.handlers}

        if _console_handler and logging.StreamHandler not in existing_handler_types:
            self.logger.addHandler(_console_handler)

        # Per i RotatingFileHandler distinguiamo per filename
        existing_filenames = {
            getattr(h, "baseFilename", None)
            for h in self.logger.handlers
            if isinstance(h, RotatingFileHandler)
        }

        if _global_file_handler and _global_file_handler.baseFilename not in existing_filenames:
            self.logger.addHandler(_global_file_handler)

        if _error_file_handler and _error_file_handler.baseFilename not in existing_filenames:
            self.logger.addHandler(_error_file_handler)

        # Handler per modulo
        if log_file:
            module_log_path = os.path.join(log_dir, log_file)
            if module_log_path not in existing_filenames:
                os.makedirs(log_dir, exist_ok=True)
                module_handler = RotatingFileHandler(
                    filename=module_log_path,
                    maxBytes=_MAX_BYTES,
                    backupCount=_BACKUP_COUNT,
                    encoding="utf-8",
                )
                module_handler.setLevel(effective_level)
                module_handler.setFormatter(_PlainFormatter())
                self.logger.addHandler(module_handler)

    def get_logger(self) -> logging.Logger:
        """Restituisce il logger configurato."""
        return self.logger
