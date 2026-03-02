"""Hardware integration for NanoAgent (Whisplay HAT)"""

from .whisplay import WhisplayDevice
from .display import DisplayRenderer

__all__ = ["WhisplayDevice", "DisplayRenderer"]
