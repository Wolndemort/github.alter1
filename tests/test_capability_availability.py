from utils.capabilities import CAPABILITIES_PROMPT, capabilities_reply
from utils.capability_catalog import CAPABILITY_CATALOG


def test_audio_isolation_is_not_advertised_when_provider_key_rejects_it():
    assert "audio_isolation" not in CAPABILITY_CATALOG["audio"]
    assert "Audio Isolation подключён и доступен" not in capabilities_reply()
    assert "Считай Audio Isolation доступным" not in CAPABILITIES_PROMPT
