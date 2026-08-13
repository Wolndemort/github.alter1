from services.voice_commands import is_voice_generation_request, voice_description


def test_mobile_voice_design_wording_is_routed_to_elevenlabs():
    assert is_voice_generation_request("получи голос Хабиба")
    assert voice_description("получи голос Хабиба") == "Хабиба"
