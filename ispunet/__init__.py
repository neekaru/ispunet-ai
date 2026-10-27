"""ISPUNet — Kualitas udara / ISPU Indonesia (KLHK).

Dibangun ulang dari APK resmi id.go.menlhk.iku.app v1.5.5 (Cordova/Ionic).
"""

__version__ = "2.0.0"

from .client import IspuClient  # noqa: F401
from .core import (  # noqa: F401
    CITY_COORDS,
    IspuCore,
    IspuError,
    StationNotFound,
    nearest,
    recommendation,
    resolve_city,
)
from .normalize import (  # noqa: F401
    OFFLINE_RECOMMENDATION,
    POLLUTANTS,
    RECOMMENDATIONS,
    STALE_HOURS,
)

__all__ = [
    "__version__",
    "IspuClient",
    "IspuCore",
    "IspuError",
    "StationNotFound",
    "recommendation",
    "nearest",
    "resolve_city",
    "CITY_COORDS",
    "POLLUTANTS",
    "RECOMMENDATIONS",
    "OFFLINE_RECOMMENDATION",
    "STALE_HOURS",
]
