from .database import Database
from config.settings import CFG

# Istanza singleton condivisa in tutta l'applicazione
db = Database(CFG.db_path)

__all__ = ["db", "Database"]
