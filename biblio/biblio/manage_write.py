from __future__ import annotations

from pathlib import Path

from biblio.manage_render import render_source_readme, render_source_toml
from biblio.models import SourceScaffold
from biblio.specs import source_root


def write_source_files(root: Path, scaffold: SourceScaffold) -> Path:
    source_dir = source_root(root) / scaffold.source_id
    source_dir.mkdir(parents=True, exist_ok=False)

    (source_dir / "source.toml").write_text(render_source_toml(scaffold), encoding="utf-8")
    (source_dir / "rules.json").write_text("[]\n", encoding="utf-8")
    (source_dir / "review_variants.json").write_text("[]\n", encoding="utf-8")
    (source_dir / "ignored_variants.json").write_text("[]\n", encoding="utf-8")
    (source_dir / "README.md").write_text(render_source_readme(scaffold), encoding="utf-8")
    return source_dir
