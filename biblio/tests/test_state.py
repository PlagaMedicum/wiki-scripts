from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from biblio.runtime_json import RuntimeJsonError
from biblio.specs import load_source_spec
from biblio.state import load_source_state, save_json_list


def _write_source_tree(
    root: Path, source_id: str, *, rules: str = "[]", review: str = "[]", ignored: str = "[]"
) -> None:
    source_dir = root / "sources" / source_id
    source_dir.mkdir(parents=True)
    source_toml = (
        textwrap.dedent(
            """
        [source]
        id = "__SOURCE_ID__"
        name = "Temporary source"
        site_lang = "be"
        family = "wikipedia"

        [search]
        insource_terms = ["ISBN 1"]
        isbns = []
        keywords = []

        [candidate]
        must_contain_all = ["ISBN 1"]
        must_contain_any = []

        [replacement]
        template_name = "Крыніцы/Тэст"
        without_pages = "__WITHOUT__"
        with_pages = "__WITH__"

        [summary]
        default_format = "__SUMMARY__"

        [pages]
        patterns = []
        reject_patterns = []

        [normalization]

        [macros]
        """
        )
        .replace("__SOURCE_ID__", source_id)
        .replace(
            "__WITHOUT__",
            "{{Крыніцы/Тэст|{entry}}}",
        )
        .replace(
            "__WITH__",
            "{{Крыніцы/Тэст|{entry}|{pages}}}",
        )
        .replace("__SUMMARY__", "Замена {{{template_name}}}")
    )
    source_dir.joinpath("source.toml").write_text(
        source_toml.strip() + "\n",
        encoding="utf-8",
    )
    source_dir.joinpath("rules.json").write_text(rules, encoding="utf-8")
    source_dir.joinpath("review_variants.json").write_text(review, encoding="utf-8")
    source_dir.joinpath("ignored_variants.json").write_text(ignored, encoding="utf-8")


def test_corrupt_rules_json_surfaces_path_context(tmp_path):
    _write_source_tree(tmp_path, "broken-rules", rules="{")
    spec = load_source_spec("broken-rules", root=tmp_path)

    with pytest.raises(RuntimeJsonError, match=r"rules\.json.*broken-rules"):
        load_source_state(spec)


def test_non_string_review_variant_surfaces_path_context(tmp_path):
    _write_source_tree(tmp_path, "broken-review", review='["ok", 1]')
    spec = load_source_spec("broken-review", root=tmp_path)

    with pytest.raises(RuntimeJsonError, match=r"review_variants\.json.*index 1"):
        load_source_state(spec)


def test_save_json_list_is_atomic_on_replace_failure(monkeypatch, tmp_path):
    path = tmp_path / "review_variants.json"
    path.write_text('["old"]', encoding="utf-8")

    def explode(self, target):
        raise OSError("boom")

    monkeypatch.setattr(Path, "replace", explode)

    with pytest.raises(RuntimeJsonError, match=r"Failed to save review_variants\.json"):
        save_json_list(path, ["new"])

    assert path.read_text(encoding="utf-8") == '["old"]'


def test_source_state_caches_and_invalidates_on_mutation(tmp_path):
    _write_source_tree(tmp_path, "cache-demo")
    spec = load_source_spec("cache-demo", root=tmp_path)
    state = load_source_state(spec)

    active_rules = state.active_rules
    review_keys = state.review_keys

    assert state.active_rules is active_rules
    assert state.review_keys is review_keys

    assert state.add_review_variant("Кніга. ISBN 1")
    assert state.active_rules is not active_rules
    assert state.review_keys is not review_keys
