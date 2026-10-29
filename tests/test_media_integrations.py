from types import SimpleNamespace
import pytest


def test_youtube_search_opens_video_and_never_downloads(monkeypatch):
    import youtube
    import yt_dlp
    calls = []
    class Downloader:
        def __init__(self, options):
            assert options['skip_download']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, query, download=False):
            assert not download
            assert query == 'ytsearch1:test'
            return {'entries': [{'url': 'https://www.youtube.com/watch?v=abc', 'title': 'Found'}]}
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Downloader)
    monkeypatch.setattr(youtube.subprocess, 'run', lambda args, **kw: calls.append(args) or SimpleNamespace(returncode=0))
    result = youtube.open_youtube('test')
    assert result['success']
    assert calls == [['open', '-a', 'Google Chrome', 'https://www.youtube.com/watch?v=abc']]


def test_youtube_open_failure_is_not_reported_as_success(monkeypatch):
    import youtube
    import yt_dlp
    class Downloader:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *a, **k): return {'entries': [{'url': 'https://www.youtube.com/watch?v=abc'}]}
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Downloader)
    monkeypatch.setattr(youtube.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stderr='not installed'))
    assert youtube.open_youtube('test')['error'] == 'browser_open_failed'


@pytest.fixture
def spotify(monkeypatch):
    import spotify_control
    monkeypatch.setattr(spotify_control, 'ensure_token', lambda: {'access_token': 'test'})
    monkeypatch.setattr(spotify_control, '_activate_desktop', lambda: None)
    monkeypatch.setattr(spotify_control, '_wait_for_device', lambda token: 'device')
    return spotify_control


def test_spotify_pause_uses_put(spotify, monkeypatch):
    calls = []
    monkeypatch.setattr(spotify, 'api', lambda *args: calls.append(args))
    assert spotify.pause()['success']
    assert calls[0][0] == 'PUT'
    assert calls[0][1].startswith('/me/player/pause?')


def test_spotify_album_plays_album_context(spotify, monkeypatch):
    calls = []
    def api(method, endpoint, token, data=None):
        calls.append((method, endpoint, data))
        if endpoint.startswith('/search'):
            assert 'type=album' in endpoint
            return {'albums': {'items': [{'name': 'Test', 'uri': 'spotify:album:test'}]}}
    monkeypatch.setattr(spotify, 'api', api)
    assert spotify.play('альбом Test')['success']
    assert calls[-1][2] == {'context_uri': 'spotify:album:test'}


def test_spotify_failures_stay_structured(spotify, monkeypatch):
    monkeypatch.setattr(spotify, 'api', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('denied')))
    result = spotify.play('test')
    assert result['success'] is False
    assert result['error'] == 'spotify_error'


def test_spotify_tokens_are_atomically_saved_with_private_permissions(tmp_path, monkeypatch):
    import json
    import stat
    import spotify_control
    path = tmp_path / 'token.json'
    monkeypatch.setattr(spotify_control, '_TOKEN_PATH', path)
    spotify_control.save_token({'access_token': 'test'})
    assert json.loads(path.read_text()) == {'access_token': 'test'}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_spotify_artist_uses_artist_context_without_extra_top_tracks_call(spotify, monkeypatch):
    calls = []
    def api(method, endpoint, token, data=None):
        calls.append((method, endpoint, data))
        if endpoint.startswith('/search'):
            return {'artists': {'items': [{'name': 'Test', 'uri': 'spotify:artist:test'}]}}
    monkeypatch.setattr(spotify, 'api', api)
    assert spotify.play('исполнителя Test')['success']
    assert calls[-1][2] == {'context_uri': 'spotify:artist:test'}
    assert len(calls) == 2


def test_spotify_empty_query_resumes_without_search(spotify, monkeypatch):
    calls = []
    monkeypatch.setattr(spotify, 'api', lambda *args: calls.append(args))
    assert spotify.play('')['success']
    assert calls == [('PUT', '/me/player/play?device_id=device', {'access_token': 'test'})]
