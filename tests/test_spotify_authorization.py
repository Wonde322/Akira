import importlib
import json
import threading
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen
from urllib.error import HTTPError
from types import SimpleNamespace


def test_spotify_auth_import_never_opens_a_browser_or_server(monkeypatch):
    import webbrowser
    import http.server
    def unexpected(*a, **k): raise AssertionError('import has side effects')
    monkeypatch.setattr(webbrowser, 'open', unexpected)
    monkeypatch.setattr(http.server, 'HTTPServer', unexpected)
    import spotify_auth
    importlib.reload(spotify_auth)


def test_spotify_oauth_checks_state_and_persists_only_exchanged_token(monkeypatch):
    import spotify_auth
    import spotify_control
    # Undo a possible class imported during the import-safety test.
    from http.server import HTTPServer
    monkeypatch.setattr(spotify_auth, 'HTTPServer', HTTPServer)
    tokens, workers = [], []
    monkeypatch.setattr(spotify_control, 'save_token', tokens.append)
    def open_browser(url):
        params = parse_qs(urlparse(url).query)
        assert params['code_challenge_method'] == ['S256']
        def callback():
            try:
                urlopen('http://127.0.0.1:8766/callback?' + urlencode({'code': 'bad', 'state': 'wrong'}), timeout=2)
                raise AssertionError('invalid state accepted')
            except HTTPError as error:
                assert error.code == 400
            with urlopen('http://127.0.0.1:8766/callback?' + urlencode({'code': 'valid', 'state': params['state'][0]}), timeout=2) as response:
                assert response.status == 200
        thread = threading.Thread(target=callback)
        workers.append(thread)
        thread.start()
        return True
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps({'access_token': 'test'}).encode()
    def exchange(request, **kwargs):
        assert parse_qs(request.data.decode())['code'] == ['valid']
        return Response()
    monkeypatch.setattr(spotify_auth.webbrowser, 'open', open_browser)
    monkeypatch.setattr(spotify_auth.urllib.request, 'urlopen', exchange)
    try:
        assert spotify_auth.authorize(timeout=2) == {'access_token': 'test'}
        assert tokens == [{'access_token': 'test'}]
    finally:
        for thread in workers: thread.join(2)
