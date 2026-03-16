import logging
import os
from logging.handlers import RotatingFileHandler

class LoggerInfo:
    """
    Factory per logger applicativi.

    Note:
    - Evita handler duplicati (comune quando moduli importano più volte il logger)
    - Log su console + file rotante (in `logs/`)
    """

    def __init__(self, name: str = __name__, log_dir: str = "logs", log_file: str = "bot.log", level=logging.DEBUG):
        self.name = name
        self.level = level

        # Crea la cartella dei log se non esiste
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, log_file)

        # Crea il logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level if self.logger.level == logging.NOTSET else self.logger.level)
        self.logger.propagate = False  # evita duplicazione log

        # Formatter avanzato
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # --- Handler Console ---
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)

        # --- Handler File con rotazione ---
        file_handler = RotatingFileHandler(
            filename=self.log_path,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        # Aggiunge handler al logger solo se non ci sono già (evita duplicati)
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)
            self.logger.addHandler(file_handler)



    def get_logger(self) -> logging.Logger:
        return self.logger
