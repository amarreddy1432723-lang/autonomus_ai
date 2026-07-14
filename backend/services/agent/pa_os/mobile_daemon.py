import time
import logging
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone

logger = logging.getLogger("nexus-pa-os")

class MobileOSDaemon:
    """
    Simulates the background native daemon running on Arceus PA OS (iOS/Android).
    Monitors system state, intercepts calls, and manages local ambient context.
    """
    def __init__(self, user_id: UUID):
        self.user_id = user_id
        self.is_monitoring = False
        self.call_history: List[Dict[str, Any]] = []
        self.system_status: Dict[str, Any] = {
            "battery_level": 100,
            "is_charging": True,
            "network_type": "5G",
            "active_apps": ["Settings", "NEXUS Mobile"],
            "screen_state": "on",
            "gps_location": {"latitude": 37.7749, "longitude": -122.4194},
        }

    def start_monitoring(self) -> None:
        self.is_monitoring = True
        logger.info(f"Arceus PA OS background monitoring started for user: {self.user_id}")

    def stop_monitoring(self) -> None:
        self.is_monitoring = False
        logger.info(f"Arceus PA OS background monitoring stopped for user: {self.user_id}")

    def update_system_status(self, battery: int, is_charging: bool, network: str, active_apps: List[str]) -> Dict[str, Any]:
        """Update system metrics broadcasted from the mobile client."""
        self.system_status.update({
            "battery_level": max(0, min(100, battery)),
            "is_charging": is_charging,
            "network_type": network,
            "active_apps": active_apps,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return self.system_status

    def intercept_call(self, caller_number: str, direction: str = "incoming") -> Dict[str, Any]:
        """Simulates native mobile phone call interception hooks."""
        call_event = {
            "call_id": str(time.time_ns()),
            "number": caller_number,
            "direction": direction,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ringing",
            "transcription": []
        }
        self.call_history.append(call_event)
        logger.info(f"Intercepted {direction} call from {caller_number}")
        return call_event

    def add_call_transcription(self, call_id: str, speaker: str, text: str) -> None:
        """Appends real-time transcribed audio text chunk during call monitoring."""
        for call in self.call_history:
            if call["call_id"] == call_id:
                call["transcription"].append({
                    "speaker": speaker,
                    "text": text,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                break
