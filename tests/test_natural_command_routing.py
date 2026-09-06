from capabilities.apps import _name
from capabilities.tool_router import _tokens, select_tool_schemas
from spotify_control import _clean_query


def _schema(name, description):
    return {"type": "function", "function": {"name": name, "description": description}}


def test_russian_app_aliases_are_normalized():
    assert _name("тг") == "Telegram"
    assert _name("телега") == "Telegram"
    assert _name("спотик") == "Spotify"
    assert _name("спотифай") == "Spotify"


def test_russian_media_aliases_expand_to_spotify_terms():
    tokens = _tokens("включи исполнителя спотик")
    assert "spotify" in tokens
    assert "music" in tokens
    assert "play" in tokens


def test_spotify_query_strips_intent_prefix():
    assert _clean_query("исполнителя Ангела") == "Ангела"
    assert _clean_query("трек Daft Punk") == "Daft Punk"


def test_volume_query_keeps_volume_tools_relevant():
    schemas = [
        _schema("get_volume", "Узнаёт текущую громкость Mac."),
        _schema("set_volume", "Устанавливает громкость Mac от 0 до 100."),
        _schema("close", "Закрывает приложение на Mac."),
    ]
    selected = select_tool_schemas("какая сейчас громкость", schemas, limit=12)
    names = {x["function"]["name"] for x in selected}
    assert "get_volume" in names
    assert "set_volume" in names


def test_spotify_command_is_selected_for_colloquial_russian_request():
    schemas = [
        _schema("play_spotify", "Открывает поиск в установленном приложении Spotify. Используй, когда пользователь просит включить трек, исполнителя, альбом или музыку в Spotify."),
        _schema("get_volume", "Узнаёт текущую громкость Mac."),
        _schema("close", "Закрывает приложение на Mac."),
    ]
    selected = select_tool_schemas("включи исполнителя Ангела в спотике", schemas, limit=12)
    names = {x["function"]["name"] for x in selected}
    assert "play_spotify" in names
