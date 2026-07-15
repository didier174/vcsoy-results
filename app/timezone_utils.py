"""
Conversion des dates/heures pour l'affichage.

Tout ce qui est stocké en base (created_at, uploaded_at, started_at, ...)
est en UTC (datetime.utcnow, voir models.py) — un choix standard côté
serveur qui évite les ambiguïtés de changement d'heure. Ce module convertit
vers l'heure locale (Est du Canada) uniquement au moment de l'affichage ;
le stockage reste inchangé.
"""

from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("America/Toronto")


def to_local(value):
    """Convertit un datetime naïf stocké en UTC vers l'heure locale."""
    if value is None:
        return None
    return value.replace(tzinfo=dt_timezone.utc).astimezone(APP_TIMEZONE)


def format_local(value, fmt="%d/%m/%Y %H:%M"):
    """Filtre Jinja (voir app/__init__.py) : formate un datetime UTC en heure
    locale ; chaîne vide si la valeur est absente."""
    local = to_local(value)
    return local.strftime(fmt) if local else ""
