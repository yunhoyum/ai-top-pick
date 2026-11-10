from sqlalchemy import Engine, create_engine

from app.core.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    """처음 쓸 때 만든다."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)
    return _engine
