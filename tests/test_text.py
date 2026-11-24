from quiet_ai.text import canonical_url, clean_text, first_line, url_id


def test_canonical_url_strips_tracking_and_normalizes():
    assert (
        canonical_url("http://WWW.Example.com/a/b/?utm_source=rss&id=7&fbclid=x#frag")
        == "https://www.example.com/a/b?id=7"
    )
    assert canonical_url("https://example.com") == "https://example.com/"
    assert canonical_url("https://news.ycombinator.com/item?id=123") == "https://news.ycombinator.com/item?id=123"


def test_url_id_ignores_tracking_params():
    assert url_id("https://x.com/a?utm_medium=feed") == url_id("https://x.com/a/")


def test_clean_text_strips_html_and_truncates():
    assert clean_text("<p>Hello&nbsp;<b>world</b> &amp; more</p>") == "Hello world & more"
    out = clean_text("word " * 200, 50)
    assert len(out) <= 50 and out.endswith("…")
    assert clean_text("   ") is None
    assert clean_text(None) is None


def test_first_line():
    assert first_line("\n\nFirst line here\nsecond") == "First line here"
