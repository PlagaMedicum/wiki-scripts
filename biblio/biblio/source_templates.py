from __future__ import annotations

import re
from collections.abc import Mapping


PLACEHOLDER_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def extract_template_placeholders(template: str) -> tuple[str, ...]:
    placeholders: list[str] = []
    seen: set[str] = set()
    index = 0

    while index < len(template):
        if template.startswith("{{", index):
            index += 2
            continue
        if template.startswith("}}", index):
            index += 2
            continue

        char = template[index]
        if char == "{":
            end = template.find("}", index + 1)
            if end == -1:
                raise ValueError(f"Unclosed placeholder in template: {template!r}")

            name = template[index + 1 : end]
            if not PLACEHOLDER_NAME_RE.fullmatch(name):
                raise ValueError(
                    f"Invalid template placeholder {name!r} in template: {template!r}"
                )
            if name not in seen:
                seen.add(name)
                placeholders.append(name)
            index = end + 1
            continue

        if char == "}":
            raise ValueError(f"Unexpected closing brace in template: {template!r}")

        index += 1

    return tuple(placeholders)


def validate_template_placeholders(
    template: str,
    allowed_fields: set[str],
    *,
    context: str,
    required_fields: set[str] | None = None,
    disallowed_fields: set[str] | None = None,
) -> None:
    placeholders = set(extract_template_placeholders(template))

    if required_fields:
        missing = required_fields - placeholders
        if missing:
            raise ValueError(
                f"{context} is missing required placeholders: {', '.join(sorted(missing))}"
            )

    if disallowed_fields:
        forbidden = placeholders & disallowed_fields
        if forbidden:
            raise ValueError(
                f"{context} uses forbidden placeholders: {', '.join(sorted(forbidden))}"
            )

    unknown = placeholders - allowed_fields
    if unknown:
        raise ValueError(
            f"{context} uses unknown placeholders: {', '.join(sorted(unknown))}"
        )


def render_template(template: str, values: Mapping[str, str]) -> str:
    for key, value in values.items():
        template = template.replace(f"{{{key}}}", value)

    if template.startswith("{{") and template.endswith("}}"):
        parts = template[2:-2].split("|")
        while parts and parts[-1] == "":
            parts.pop()
        template = "{{" + "|".join(parts) + "}}"
    return template
