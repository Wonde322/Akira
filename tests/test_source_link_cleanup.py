from desktop_app.source_links import extract_sources


def test_source_footer_becomes_chips_without_duplicate_text():
    body, sources = extract_sources('Ответ.\n\nИсточник: [24smi.org](https://24smi.org/a), [Genius](https://genius.com/b).')
    assert body == 'Ответ.'
    assert len(sources) == 2


def test_bare_urls_source_footer_is_removed():
    body, sources = extract_sources('Ответ.\nИсточники: https://example.org и https://other.org')
    assert body == 'Ответ.'
    assert len(sources) == 2


def test_inline_link_text_and_meaningful_source_explanation_survive():
    body, sources = extract_sources('Смотри [статью](https://example.org).\nИсточник: интервью автора, опубликованное вчера.')
    assert 'Смотри статью.' in body
    assert 'интервью автора' in body


def test_unlinked_source_text_is_preserved():
    assert extract_sources('Источник: Genius.')[0] == 'Источник: Genius.'
