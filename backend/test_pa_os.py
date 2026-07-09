import pytest
from uuid import uuid4
from services.agent.pa_os.mobile_daemon import MobileOSDaemon
from services.agent.pa_os.voice_pipeline import VoiceTelemetryTracker, InterruptionDetector

def test_mobile_os_daemon():
    user_id = uuid4()
    daemon = MobileOSDaemon(user_id)
    
    daemon.start_monitoring()
    assert daemon.is_monitoring is True
    
    # Update system status
    status = daemon.update_system_status(85, False, "4G", ["Browser", "Maps"])
    assert status["battery_level"] == 85
    assert status["is_charging"] is False
    assert status["network_type"] == "4G"
    assert "Maps" in status["active_apps"]
    
    # Intercept incoming call
    call = daemon.intercept_call("+15550199", "incoming")
    assert call["number"] == "+15550199"
    assert call["direction"] == "incoming"
    assert call["status"] == "ringing"
    
    # Append call transcription
    daemon.add_call_transcription(call["call_id"], "user", "Hello, who is this?")
    assert len(daemon.call_history[0]["transcription"]) == 1
    assert daemon.call_history[0]["transcription"][0]["text"] == "Hello, who is this?"
    
    daemon.stop_monitoring()
    assert daemon.is_monitoring is False

def test_voice_telemetry_and_interruption():
    tracker = VoiceTelemetryTracker()
    
    # Log telemetry
    log = tracker.log_latency(
        session_id="voice-telemetry-test",
        stt_ms=150.0,
        llm_ms=450.0,
        tts_ms=200.0,
        network_ms=25.0
    )
    assert log["total_roundtrip_ms"] == 825.0
    assert log["quality_grade"] == "fair"
    
    averages = tracker.average_latency()
    assert averages["avg_rtt_ms"] == 825.0
    
    # Test interruption detection
    detector = InterruptionDetector(energy_threshold=0.5)
    assert detector.should_interrupt(mic_energy_level=0.7, assistant_is_speaking=True) is True
    assert detector.should_interrupt(mic_energy_level=0.3, assistant_is_speaking=True) is False
