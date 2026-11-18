from __future__ import annotations

from biblio.models import CandidateSpec, NormalizationOptions, SourceSpec
from biblio.runtime import LoadedPage, PageEdit, WikiClientPool


def _spec(tmp_path, source_id: str = "demo") -> SourceSpec:
    return SourceSpec(
        source_dir=tmp_path / "sources" / source_id,
        source_id=source_id,
        name="Demo",
        site_lang="be",
        family="wikipedia",
        insource_terms=("term",),
        isbns=(),
        keywords=(),
        candidate=CandidateSpec(must_contain_all=("term",), must_contain_any=()),
        template_name="Крыніцы/Тэст",
        template_without_pages="{{Крыніцы/Тэст}}",
        template_with_pages="{{Крыніцы/Тэст||{pages}}}",
        default_summary_format="Замена {{Крыніцы/Тэст}}",
        page_patterns=(),
        reject_patterns=(),
        regex_rules=(),
        alias_rules=(),
        normalization=NormalizationOptions(),
    )


def test_wiki_client_pool_reuses_client_for_same_wiki(tmp_path):
    create_calls = []
    load_calls = []

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title = title

    class FakePywikibot:
        Page = FakePage

    class FakeSite:
        pass

    def fake_create_site(spec, pywikibot_dir):
        create_calls.append((spec.source_id, pywikibot_dir))
        return FakePywikibot, FakeSite()

    def fake_load_titles(site, query, limit):
        load_calls.append((site, query, limit))
        return 0, []

    pool = WikiClientPool(
        actual_root=tmp_path,
        create_site=fake_create_site,
        load_titles_func=fake_load_titles,
    )

    first = pool.get(_spec(tmp_path, "first"))
    second = pool.get(_spec(tmp_path, "second"))

    assert first is second
    assert create_calls == [("first", tmp_path / ".pywikibot")]
    assert first.page("Title").title == "Title"
    assert first.load_titles("query", 10) == (0, [])
    assert len(load_calls) == 1


def test_wiki_client_saves_page_via_edit_request(tmp_path):
    class FakePage:
        def __init__(self, site=None, title=None) -> None:
            self.text = "old"
            self.saved_kwargs = None
            self.title = title

        def save(self, **kwargs) -> None:
            self.saved_kwargs = kwargs

    class FakePywikibot:
        Page = FakePage

    class FakeSite:
        pass

    def fake_create_site(spec, pywikibot_dir):
        return FakePywikibot, FakeSite()

    pool = WikiClientPool(
        actual_root=tmp_path,
        create_site=fake_create_site,
        load_titles_func=lambda *args: (0, []),
    )
    client = pool.get(_spec(tmp_path))
    page = FakePage()

    client.save_page(page, PageEdit(text="new", summary="Summary", minor=True))

    assert page._text == "new"
    assert page.saved_kwargs == {
        "summary": "Summary",
        "minor": True,
        "bot": True,
        "force": True,
        "asynchronous": False,
    }


def test_wiki_client_load_page_reuses_loaded_page_object(tmp_path):
    class FakePage:
        def __init__(self, site=None, title=None) -> None:
            self.site = site
            self.title = title
            self.text = f"text for {title}"
            self.saved_kwargs = None

        def save(self, **kwargs) -> None:
            self.saved_kwargs = kwargs

    class FakePywikibot:
        Page = FakePage

    class FakeSite:
        pass

    def fake_create_site(spec, pywikibot_dir):
        return FakePywikibot, FakeSite()

    pool = WikiClientPool(
        actual_root=tmp_path,
        create_site=fake_create_site,
        load_titles_func=lambda *args: (0, []),
    )
    client = pool.get(_spec(tmp_path))

    loaded = client.load_page("Loaded title")
    client.save_page(loaded.page, PageEdit(text="new text", summary="Summary", minor=False))

    assert loaded == LoadedPage(
        page=loaded.page,
        title="Loaded title",
        text="text for Loaded title",
    )
    assert loaded.page._text == "new text"
    assert loaded.page.saved_kwargs == {
        "summary": "Summary",
        "minor": False,
        "bot": True,
        "force": True,
        "asynchronous": False,
    }


def test_wiki_client_can_reconnect(tmp_path):
    login_calls = []

    class FakePywikibot:
        Page = object

    class FakeSite:
        def login(self):
            login_calls.append("login")

    def fake_create_site(spec, pywikibot_dir):
        return FakePywikibot, FakeSite()

    pool = WikiClientPool(
        actual_root=tmp_path,
        create_site=fake_create_site,
        load_titles_func=lambda *args: (0, []),
    )

    client = pool.get(_spec(tmp_path))
    client.reconnect()

    assert login_calls == ["login"]


def test_wiki_client_primes_write_session_once_until_reconnect(tmp_path):
    token_reads = []
    login_calls = []

    class FakeTokens(dict):
        def __getitem__(self, key):
            token_reads.append(key)
            return super().__getitem__(key)

    class FakePywikibot:
        Page = object

        class config:
            put_throttle = 0.2
            minthrottle = 0.0
            max_retries = 3
            retry_wait = 1
            retry_max = 8
            maxlag = 5

    class FakeSite:
        def __init__(self) -> None:
            self.tokens = FakeTokens({"csrf": "token"})

        def login(self):
            login_calls.append("login")

    def fake_create_site(spec, pywikibot_dir):
        return FakePywikibot, FakeSite()

    pool = WikiClientPool(
        actual_root=tmp_path,
        create_site=fake_create_site,
        load_titles_func=lambda *args: (0, []),
    )
    client = pool.get(_spec(tmp_path))

    assert client.prime_write_session() is True
    assert client.prime_write_session() is False
    assert token_reads == ["csrf"]
    client.reconnect()
    assert login_calls == ["login"]
    assert client.prime_write_session() is True
    assert token_reads == ["csrf", "csrf"]
