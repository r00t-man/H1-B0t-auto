"""Плоский key-value стейт на файлах — без БД, переживает рестарт процесса.

Один ключ = один файл в STATE_DIR — минимум зависимостей, поведение прозрачно
видно из файловой системы (полезно для отладки при поддержке чужой
инсталляции).
"""
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def get_state(key: str, default: str = "") -> str:
    path = STATE_DIR / key
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8").strip()


def set_state(key: str, value: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / key).write_text(value, encoding="utf-8")
