import time
import logging
from typing import Dict, Any, List

logger = logging.getLogger("nexus-voice-pipeline")

class VoiceTelemetryTracker:
    """Tracks latency metrics across the real-time voice pipeline (STT -> LLM -> TTS)."""
    def __init__(self):
        self.latency_records: List[Dict[str, Any]] = []

    def log_latency(
        self,
        session_id: str,
        stt_ms: float,
        llm_ms: float,
        tts_ms: float,
        network_ms: float = 20.0
    ) -> Dict[str, Any]:
        total_roundtrip = stt_ms + llm_ms + tts_ms + network_ms
        record = {
            "session_id": session_id,
            "speech_to_text_ms": stt_ms,
            "llm_reasoning_ms": llm_ms,
            "text_to_speech_ms": tts_ms,
            "network_delay_ms": network_ms,
            "total_roundtrip_ms": total_roundtrip,
            "quality_grade": "excellent" if total_roundtrip < 800 else "fair" if total_roundtrip < 1500 else "poor",
            "timestamp": time.time()
        }
        self.latency_records.append(record)
        logger.info(f"Voice pipeline latency logged: {total_roundtrip}ms [Grade: {record['quality_grade']}]")
        return record

    def average_latency(self) -> Dict[str, float]:
        if not self.latency_records:
            return {"avg_rtt_ms": 0.0, "avg_llm_ms": 0.0}
        total = len(self.latency_records)
        return {
            "avg_stt_ms": sum(r["speech_to_text_ms"] for r in self.latency_records) / total,
            "avg_llm_ms": sum(r["llm_reasoning_ms"] for r in self.latency_records) / total,
            "avg_tts_ms": sum(r["text_to_speech_ms"] for r in self.latency_records) / total,
            "avg_rtt_ms": sum(r["total_roundtrip_ms"] for r in self.latency_records) / total,
        }

class InterruptionDetector:
    """Simulates real-time audio energy interruption detection logic."""
    def __init__(self, energy_threshold: float = 0.6):
        self.energy_threshold = energy_threshold

    def should_interrupt(self, mic_energy_level: float, assistant_is_speaking: bool) -> bool:
        """Determines if the assistant should immediately stop speaking because the user spoke."""
        if assistant_is_speaking and mic_energy_level >= self.energy_threshold:
            logger.info("User interruption detected. Halting assistant voice output stream.")
            return True
        return False
