# config.py
# Все настройки берутся из файла .env (лежит рядом с ботом, в git НЕ попадает).
# Пример — в .env.example
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    """Простой загрузчик .env: KEY=VALUE, строки с # игнорируются."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / ".env")


def _int_list(value: str) -> list[int]:
    return [int(x) for x in value.replace(";", ",").replace(" ", ",").split(",") if x.strip()]


BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан. Впиши его в файл .env")

# ID администраторов (через запятую). Плюс к ним — админы из таблицы admins в базе.
ADMIN_IDS = _int_list(os.environ.get("ADMIN_IDS", ""))

# ID админской группы
_admin_group = os.environ.get("ADMIN_GROUP_ID", "").strip()
if not _admin_group.lstrip("-").isdigit():
    raise SystemExit("ADMIN_GROUP_ID не задан или неверный. Впиши ID админской группы в файл .env")
ADMIN_GROUP_ID = int(_admin_group)

# Прокси/туннель. Например socks5://127.0.0.1:1080 . Пусто — без прокси.
PROXY_URL = os.environ.get("PROXY_URL", "").strip()

# Путь к базе данных (относительно папки бота)
DB_PATH = str(BASE_DIR / os.environ.get("DB_PATH", "bot_database.db"))

# Интервалы для рассылок (в минутах)
INTERVALS = {
    "30 минут": 30,
    "1 час": 60,
    "90 минут": 90,
    "2 часа": 120
}
