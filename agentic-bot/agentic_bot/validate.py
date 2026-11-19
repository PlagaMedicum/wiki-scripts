"""Wikitext proposal validation against the target wiki.

Contract:
- Regression detection: only problems NEWLY INTRODUCED by the proposed content
  are reported (diffed against the base page content). Pre-existing problems
  are out of scope.
- Classification: ``errors`` are confirmed and block approval/publication;
  ``warnings`` are confirmed but non-blocking; ``unverified`` records checks
  that could not be completed. No check silently succeeds.
- Never a false success: any API failure or unrecognised response shape turns
  into ``unverified``, and the summary never claims success while anything is
  unverified.
- Scope: wikitext pages only; other content models (JS/CSS/...) are skipped
  with an unverified note.

Names of linked pages and transcluded templates come from the parser
(``action=parse`` ``links``/``iwlinks``/``templates``), which resolves
namespaces, magic words, and interwiki prefixes authoritatively; fragment
names the parser lists nowhere (plain-form ``[[en:...]]`` interwiki links are
invisible in its output) are classified against ``siteinfo interwikimap``.
Regex extraction is used only for what the parser does not expose: section
fragments (``[[Page#anchor]]``) and template named parameters. This is a
checker, not a wikitext parser; ambiguous constructs degrade to
``unverified``, never to a guessed verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_NOISE_RE = re.compile(
    r"<!--.*?-->|<nowiki>.*?</nowiki>|<pre>.*?</pre>|<code>.*?</code>"
    r"|<syntaxhighlight[^>]*>.*?</syntaxhighlight>",
    re.DOTALL | re.IGNORECASE,
)
_LINK_RE = re.compile(r"\[\[([^\[\]|#]*)(#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
_TEMPLATE_NAME_RE = re.compile(r"(?<!\{)\{\{\s*([^|}{#]*?)\s*(?:\||\}\})")
_TEMPLATE_WITH_ARGS_RE = re.compile(r"(?<!\{)\{\{\s*([^|}{#]*?)\s*\|")
_TEMPLATE_ARGS_RE = re.compile(r"(?<!\{)\{\{\s*([^|}{#]*?)\s*\|([^{}\[\]]*)\}\}")
_TEMPLATE_KEY_PREFIXES = ("subst:", "safesubst:", "template:", "шаблон:")

_INVENTORY_PROPS = "parsewarnings|links|iwlinks|templates|categories|images"
_BATCH_SIZE = 50


@dataclass(frozen=True)
class ParseInventory:
    """Parser-authoritative name sets of one rendered wikitext revision."""

    links: frozenset[str]  # local internal links (all namespaces), incl. transclusions
    iwlinks: frozenset[str]  # interwiki links (out of validation scope)
    templates: frozenset[str]  # transclusion targets
    categories: frozenset[str]  # category names (no namespace prefix)
    images: frozenset[str]  # file names (no namespace prefix)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one proposal version against its base revision."""

    version: int
    base_revid: int
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def is_fresh(self, version: int, base_revid: int) -> bool:
        return self.version == version and self.base_revid == base_revid

    def summary(self) -> str:
        if self.errors:
            return (
                f"VALIDATION FAILED: {len(self.errors)} error(s), "
                f"{len(self.warnings)} warning(s), {len(self.unverified)} unverified"
            )
        if self.unverified:
            return (
                f"VALIDATION INCOMPLETE: {len(self.warnings)} warning(s), "
                f"{len(self.unverified)} check(s) unverified"
            )
        if self.warnings:
            return f"VALIDATION: {len(self.warnings)} warning(s), no blocking errors"
        return "VALIDATION PASSED: no new issues found"


def describe_validation(result: ValidationResult | None) -> list[str]:
    """Plain-text lines (summary first) for CLI output."""
    if result is None:
        return []
    lines = [result.summary()]
    lines += [f"error: {e}" for e in result.errors]
    lines += [f"warning: {w}" for w in result.warnings]
    lines += [f"unverified: {u}" for u in result.unverified]
    return lines


# ---------------------------------------------------------------------------
# Extraction: fragments and template parameters only (target names come from
# the parser). Deliberately not a wikitext parser.
# ---------------------------------------------------------------------------


def _norm_title(name: str) -> str:
    return name.replace("_", " ").strip()


def _key(name: str) -> str:
    """Comparison key for link/transclusion names: one leading link-colon
    stripped (``[[:Page]]`` == ``[[Page]]``), underscores normalised,
    casefolded."""
    if name.startswith(":"):
        name = name[1:]
    return name.replace("_", " ").strip().casefold()


def _norm_anchor(anchor: str) -> str:
    return anchor.replace("_", " ").strip().casefold()


def extract_link_fragments(text: str) -> dict[str, frozenset[str]]:
    """Section fragments per link target; "" anchors are plain links.

    All targets are kept (namespaced/interwiki included): interwiki targets
    are filtered later against the parser's iwlinks listing and the siteinfo
    interwikimap. Fragment pairs on targets the parser confirms missing are
    skipped in the anchor check.
    """
    anchors: dict[str, set[str]] = {}
    for match in _LINK_RE.finditer(_NOISE_RE.sub(" ", text)):
        target, anchor = match.group(1).strip(), match.group(2) or ""
        if not target and not anchor:
            continue
        anchors.setdefault(_norm_title(target), set()).add(
            anchor.lstrip("#").replace("_", " ").strip()
        )
    return {k: frozenset(v) for k, v in anchors.items()}


def _template_key(raw: str) -> str:
    """Diff key for one transclusion invocation.

    MediaWiki namespace semantics only: modifiers and explicit template
    namespaces are stripped so ``{{X}}`` and ``{{Template:X}}`` key alike;
    other namespaces (``{{Вікіпедыя:X}}``) are kept as-is.
    """
    name = _norm_title(raw)
    lowered = name.casefold()
    for prefix in _TEMPLATE_KEY_PREFIXES:
        if lowered.startswith(prefix):
            name = _norm_title(name[len(prefix) :])
            break
    return name


def _strip_template_namespace(name: str) -> str:
    """Drop an explicit template-namespace prefix ('Template:' / local
    'Шаблон:'); other namespaces are left alone."""
    prefix, sep, rest = name.partition(":")
    if sep and prefix.casefold() in ("template", "шаблон"):
        return rest.strip()
    return name


def _template_query_title(key: str, parser_templates: frozenset[str]) -> str:
    """Title for TemplateData queries and the missing-template skip.

    Maps the invocation through the parser's own transclusion listing so the
    local namespace spelling ('Шаблон:X' on be.wiki) is used verbatim — the
    parser's names are the authority, not our namespace guesses. Falls back
    to ``key`` for namespaced invocations and to the English ``Template:``
    prefix for bare ones (MediaWiki normalises either way).
    """
    wanted = _key(key)
    for title in parser_templates:
        if _key(_strip_template_namespace(title)) == wanted:
            return title
    if ":" in key:
        return key
    return f"Template:{key}"


def extract_template_params(text: str) -> tuple[dict[str, frozenset[str]], int]:
    """Named parameters per transclusion key, plus a count of invocations
    whose arguments cannot be parameter-checked (nested/complex)."""
    clean = _NOISE_RE.sub(" ", text)
    params: dict[str, set[str]] = {}
    for match in _TEMPLATE_NAME_RE.finditer(clean):
        key = _template_key(match.group(1))
        if key:
            params.setdefault(key, set())
    for match in _TEMPLATE_ARGS_RE.finditer(clean):
        key = _template_key(match.group(1))
        if not key:
            continue
        named = params.setdefault(key, set())
        for part in match.group(2).split("|"):
            if "=" in part:
                name = part.split("=", 1)[0].strip().casefold()
                if name:
                    named.add(name)
    complex_args = max(
        0,
        len(_TEMPLATE_WITH_ARGS_RE.findall(clean)) - len(_TEMPLATE_ARGS_RE.findall(clean)),
    )
    return {k: frozenset(v) for k, v in params.items()}, complex_args


# ---------------------------------------------------------------------------
# API response interpretation (defensive: unknown shapes raise ValueError)
# ---------------------------------------------------------------------------


def _as_dict(value: Any, key: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"response is not a dict ({key})")
    inner = value.get(key)
    if not isinstance(inner, dict):
        raise ValueError(f"response has no {key!r} object")
    return inner


def _pages_list(query: dict) -> list[dict]:
    pages = query.get("pages")
    if isinstance(pages, dict):  # formatversion 1
        pages = list(pages.values())
    if not isinstance(pages, list) or not all(isinstance(p, dict) for p in pages):
        raise ValueError("response has no page list")
    return pages


def _entries(value: Any) -> list[dict]:
    """Normalise a list-or-keyed-dict of entries to a list of dicts."""
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
        raise ValueError("response has no entry list")
    return value


def _resolve(query: dict, requested: str) -> tuple[dict | None, bool]:
    """Map a requested title to its final page entry; returns (entry, via_redirect)."""
    norm_map = {e.get("from"): e.get("to") for e in _entries(query.get("normalized", []))}
    redirect_map = {e.get("from"): e.get("to") for e in _entries(query.get("redirects", []))}
    by_title = {p.get("title"): p for p in _pages_list(query)}
    current = norm_map.get(requested, requested)
    via_redirect = False
    while current in redirect_map:
        current = redirect_map[current]
        via_redirect = True
    return by_title.get(current), via_redirect


def _parse_parts(resp: Any, want_warnings: bool, want_sections: bool) -> tuple[set[str], set[str]]:
    """Extract the requested parse fields; unknown shapes raise (-> unverified)."""
    parse = _as_dict(resp, "parse")
    warnings: set[str] = set()
    if want_warnings:
        if "parsewarnings" not in parse:
            raise ValueError("response has no parsewarnings")
        raw_warnings = parse["parsewarnings"]
        if isinstance(raw_warnings, dict):  # formatversion 1
            raw_warnings = list(raw_warnings.values())
        if not isinstance(raw_warnings, list) or not all(isinstance(w, str) for w in raw_warnings):
            raise ValueError("bad parsewarnings")
        warnings = set(raw_warnings)
    anchors: set[str] = set()
    if want_sections:
        if "sections" not in parse:
            raise ValueError("response has no sections")
        for s in _entries(parse["sections"]):
            anchor = s.get("anchor")
            if not isinstance(anchor, str):
                raise ValueError("bad section entry")
            anchors.add(anchor)
    return warnings, anchors


def _parse_inventory(resp: Any) -> ParseInventory:
    """Parser-authoritative name sets; any malformed shape raises."""
    parse = _as_dict(resp, "parse")

    def title_set(key: str) -> frozenset[str]:
        out: set[str] = set()
        for entry in _entries(parse.get(key)):
            title = entry.get("title")
            if not isinstance(title, str):
                raise ValueError(f"parse {key} entry without title")
            out.add(title)
        return frozenset(out)

    categories: set[str] = set()
    for entry in _entries(parse.get("categories")):
        name = entry.get("category")
        if not isinstance(name, str):
            raise ValueError("parse categories entry without name")
        categories.add(name)

    images = parse.get("images")
    if not isinstance(images, list) or not all(isinstance(i, str) for i in images):
        raise ValueError("parse images is not a list of file names")

    return ParseInventory(
        links=title_set("links"),
        iwlinks=title_set("iwlinks"),
        templates=title_set("templates"),
        categories=frozenset(categories),
        images=frozenset(images),
    )


def _templatedata_param_names(resp: Any) -> set[str] | None:
    """Valid parameter names incl. aliases, or None when TemplateData is absent."""
    if not isinstance(resp, dict) or "pages" not in resp:
        raise ValueError("response has no pages")
    entries = _entries(resp["pages"])
    if not entries:
        return None
    entry = entries[0]
    if "missing" in entry or "params" not in entry:
        return None
    params = entry["params"]
    if not isinstance(params, dict):
        raise ValueError("bad templatedata params")
    names = set()
    for pname, pdef in params.items():
        names.add(str(pname).casefold())
        if not isinstance(pdef, dict):
            raise ValueError("bad templatedata param entry")
        aliases = pdef.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise ValueError("bad templatedata aliases")
        names.update(a.casefold() for a in aliases)
    return names


def _interwiki_prefixes(client: Any) -> set[str]:
    """Interwiki prefixes from siteinfo — the authoritative local-vs-interwiki
    distinction. Plain-form ``[[en:Earth]]`` links are invisible to parser
    output (verified live), so fragment names the parser does not list are
    classified against this map."""
    resp = _as_dict(
        client.query_api("query", meta="siteinfo", siprop="interwikimap", formatversion=2),
        "query",
    )
    prefixes: set[str] = set()
    for entry in _entries(resp.get("interwikimap")):
        prefix = entry.get("prefix")
        if not isinstance(prefix, str):
            raise ValueError("interwikimap entry without prefix")
        prefixes.add(prefix.casefold())
    return prefixes


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_proposal(client: Any, proposal: Any) -> ValidationResult:
    """Validate the proposed wikitext of one proposal version.

    Never raises: every completed, failed, or skipped check is reflected in the
    returned result. ``client`` is any object with a WikiClient-style
    ``query_api(action, **params) -> dict``; None means no client available.
    """
    version = proposal.current_version
    base_revid = proposal.page.revid
    title = proposal.page.title
    original = proposal.page.content
    proposed = proposal.proposed_content

    errors: list[str] = []
    warnings: list[str] = []
    unverified: list[str] = []

    def done() -> ValidationResult:
        return ValidationResult(
            version, base_revid, tuple(errors), tuple(warnings), tuple(unverified)
        )

    if client is None:
        unverified.append("MediaWiki client unavailable — no wiki checks were run")
        return done()

    # Scope gate: wikitext pages only.
    try:
        query = _as_dict(
            client.query_api("query", prop="info", titles=title, formatversion=2), "query"
        )
        pages = _pages_list(query)
    except Exception as exc:
        unverified.append(f"content model check failed ({exc}) — validation aborted")
        return done()
    if not pages:
        unverified.append("content model check returned no page data — validation aborted")
        return done()
    model = pages[0].get("contentmodel")
    if model is not None and model != "wikitext":
        unverified.append(f"page content model '{model}' is not wikitext — validation skipped")
        return done()
    if model is None and "missing" not in pages[0]:
        unverified.append("content model not reported by the API")

    # Render + inventory in one parse per revision: the parser is the
    # authority for link/template/category/file names (it resolves
    # namespaces, magic words, and interwiki prefixes); sections come from
    # the same call for same-page anchors.
    old_inv: ParseInventory | None = None
    try:
        resp_old = client.query_api(
            "parse",
            text=original,
            title=title,
            prop=_INVENTORY_PROPS,
            contentmodel="wikitext",
            formatversion=2,
        )
        old_warnings, _ = _parse_parts(resp_old, want_warnings=True, want_sections=False)
        old_inv = _parse_inventory(resp_old)
    except Exception as exc:
        old_warnings = None
        unverified.append(f"render check of the base revision failed ({exc})")
    new_inv: ParseInventory | None = None
    proposed_sections: set[str] = set()
    try:
        resp_new = client.query_api(
            "parse",
            text=proposed,
            title=title,
            prop=_INVENTORY_PROPS + "|sections",
            contentmodel="wikitext",
            formatversion=2,
        )
        new_warnings, proposed_sections = _parse_parts(
            resp_new, want_warnings=True, want_sections=True
        )
        new_inv = _parse_inventory(resp_new)
    except Exception as exc:
        new_warnings = None
        unverified.append(f"render check of the proposed content failed ({exc})")

    # Render check: parser warnings, diffed against the base revision.
    if old_warnings is not None and new_warnings is not None:
        for w in sorted(new_warnings - old_warnings):
            warnings.append(f"new parser warning: {w}")

    missing_keys: set[str] = set()
    if old_inv is not None and new_inv is not None:
        old_titles = old_inv.links | old_inv.templates
        new_titles = new_inv.links | new_inv.templates
        introduced_templates = new_inv.templates - old_inv.templates
        introduced_targets = sorted((new_titles - old_titles) | introduced_templates)
        link_only = new_inv.links - new_inv.templates

        # Existence and redirect usage of newly introduced targets. One batch
        # covers links and transclusions together (parse.links lists both), so
        # a missing transclusion is reported exactly once.
        for chunk in _chunks(introduced_targets, _BATCH_SIZE):
            try:
                batch = _as_dict(
                    client.query_api(
                        "query",
                        prop="info",
                        titles="|".join(chunk),
                        redirects=1,
                        formatversion=2,
                    ),
                    "query",
                )
            except Exception as exc:
                unverified.append(f"existence check for newly introduced targets failed ({exc})")
                continue
            try:
                for name in chunk:
                    entry, via_redirect = _resolve(batch, name)
                    if entry is None:
                        unverified.append(f"target '{name}' was not returned by the API")
                    elif "missing" in entry:
                        missing_keys.add(_key(name))
                        if name in introduced_templates:
                            errors.append(
                                f"newly introduced transclusion '{name}' does not exist on the wiki"
                            )
                        else:
                            warnings.append(
                                f"newly introduced link '{name}' does not exist on the wiki "
                                "(red link; human attention required)"
                            )
                    elif via_redirect and name in link_only:
                        warnings.append(
                            f"newly introduced link '{name}' redirects to '{entry.get('title')}'"
                        )
            except Exception as exc:
                unverified.append(f"existence check for newly introduced targets failed ({exc})")

        # Fragment names/pairs: regressions only. The parser lists local and
        # colon-form interwiki targets, but plain-form interwiki links are
        # invisible in its output (verified live); names it lists nowhere are
        # classified against siteinfo interwikimap — authoritative, not a
        # string heuristic.
        old_fragments = extract_link_fragments(original)
        new_fragments = extract_link_fragments(proposed)
        introduced_names = sorted(n for n in new_fragments if n and n not in old_fragments)
        introduced_pairs = sorted(
            (name, fragment)
            for name, anchors in new_fragments.items()
            for fragment in anchors - old_fragments.get(name, frozenset())
            if fragment
        )
        inventory_keys = {_key(t) for t in old_titles | new_titles}
        iwlink_keys = {_key(t) for t in old_inv.iwlinks | new_inv.iwlinks}
        to_classify = [
            n
            for n in set(introduced_names) | {n for n, _ in introduced_pairs if n}
            if ":" in n.lstrip(":") and _key(n) not in inventory_keys and _key(n) not in iwlink_keys
        ]
        iw_prefixes: set[str] = set()
        classify_failed = False
        if to_classify:
            try:
                iw_prefixes = _interwiki_prefixes(client)
            except Exception as exc:
                classify_failed = True
                unverified.append(f"interwiki classification unavailable ({exc})")

        def _is_interwiki(name: str) -> bool:
            stripped = name[1:] if name.startswith(":") else name
            prefix = stripped.split(":", 1)[0].casefold()
            return bool(prefix) and (prefix in iw_prefixes or classify_failed)

        # Section anchors of newly introduced fragment links. Interwiki pairs
        # are out of scope (counted at name level), pairs on confirmed-missing
        # targets are already reported; everything else is checked
        # against the target page's real headings. Mismatch stays
        # warning-level because headings can also come from templates and raw
        # HTML anchors.
        for name, fragment in introduced_pairs:
            if not name:  # same-page anchor: the proposed content's own sections
                if _norm_anchor(fragment) not in {_norm_anchor(s) for s in proposed_sections}:
                    warnings.append(
                        f"section link '[[#{fragment}]]' does not match any section heading"
                    )
                continue
            key = _key(name)
            if key in missing_keys:
                continue  # already reported as missing
            if key not in inventory_keys and (key in iwlink_keys or _is_interwiki(name)):
                continue  # interwiki target: out of scope, counted below
            target = name[1:] if name.startswith(":") else name
            try:
                resp = client.query_api(
                    "parse", page=target, prop="sections", redirects=1, formatversion=2
                )
                _, section_anchors = _parse_parts(resp, want_warnings=False, want_sections=True)
            except Exception as exc:
                unverified.append(f"section anchors of '{name}' could not be checked ({exc})")
                continue
            if _norm_anchor(fragment) not in {_norm_anchor(s) for s in section_anchors}:
                warnings.append(
                    f"section link '[[{name}#{fragment}]]' does not match any section heading"
                )

        # Construct types outside the checked scope are counted once, never
        # guessed at: interwiki links (parser iwlinks plus plain-form names the
        # parser hides), categories, and files have no existence contract here.
        plain_interwiki_new = [
            n
            for n in introduced_names
            if _key(n) not in inventory_keys
            and _key(n) not in iwlink_keys
            and ":" in n.lstrip(":")
            and _is_interwiki(n)
        ]
        out_of_scope = (
            len(new_inv.iwlinks - old_inv.iwlinks)
            + len(new_inv.categories - old_inv.categories)
            + len(new_inv.images - old_inv.images)
            + len(plain_interwiki_new)
        )
        if out_of_scope:
            unverified.append(
                f"{out_of_scope} newly introduced link(s) to interwiki, category, or file "
                "targets were not checked (out of scope)"
            )

    # Template parameters (TemplateData): only parameters newly introduced by
    # the proposal are checked; absence of TemplateData is unverified, never a
    # pass.
    old_params, old_complex = extract_template_params(original)
    new_params, new_complex = extract_template_params(proposed)
    introduced_params = {
        key: names - old_params.get(key, frozenset())
        for key, names in new_params.items()
        if names - old_params.get(key, frozenset())
    }
    introduced_complex = new_complex - old_complex
    if introduced_complex > 0:
        unverified.append(
            f"parameter check skipped for {introduced_complex} template invocation(s) "
            "with complex arguments (newly introduced)"
        )
    parser_templates: frozenset[str] = frozenset()
    if old_inv is not None and new_inv is not None:
        parser_templates = old_inv.templates | new_inv.templates
    for key in sorted(introduced_params):
        template_title = _template_query_title(key, parser_templates)
        if _key(template_title) in missing_keys:
            continue  # existence error already reported; TemplateData is moot
        try:
            valid = _templatedata_param_names(
                client.query_api("templatedata", titles=template_title, formatversion=2)
            )
        except Exception as exc:
            unverified.append(f"TemplateData for '{template_title}' failed ({exc})")
            continue
        if valid is None:
            unverified.append(
                f"TemplateData for '{template_title}' is not available (parameter checks skipped)"
            )
            continue
        for param in sorted(introduced_params[key]):
            if param not in valid:
                warnings.append(
                    f"unknown parameter '{param}' of template '{template_title}' "
                    "(not in TemplateData)"
                )

    return done()
