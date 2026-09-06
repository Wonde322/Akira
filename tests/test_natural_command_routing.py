from computer_state import Application, ApplicationResolver
from capabilities.tool_router import _tokens, select_tool_schemas
from spotify_control import _clean_query


def _schema(name, description):
    return {"type": "function", "function": {"name": name, "description": description}}


def test_russian_colloquialisms_resolve_against_real_app_names():
    resolver = ApplicationResolver()
    resolver._cache = [
        Application("Telegram", "/Applications/Telegram.app", "org.telegram.desktop"),
        Application("Spotify", "/Applications/Spotify.app", "com.spotify.client"),
        Application("Google Chrome", "/Applications/Google Chrome.app", "com.google.Chrome"),
    ]
    assert resolver.resolve("тг").name == "Telegram"
    assert resolver.resolve("телега").name == "Telegram"
    assert resolver.resolve("спотик").name == "Spotify"
    assert resolver.resolve("спотифай").name == "Spotify"


def test_tokenization_is_generic_not_application_alias_driven():
    tokens = _tokens("включи исполнителя спотик")
    assert "vklyuchi" in tokens
    assert "ispolnitelya" in tokens
    assert "spotik" in tokens


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
