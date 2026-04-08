use std::collections::BTreeSet;

#[derive(Debug, Clone)]
pub struct ParseResult {
    pub titles: Vec<String>,
    pub warnings: Vec<String>,
}

pub fn normalize_title(input: &str) -> String {
    let trimmed = input.trim().replace('_', " ");
    let collapsed = trimmed
        .split_whitespace()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    if let Some((prefix, rest)) = collapsed.split_once(':') {
        let mut chars = prefix.trim().chars();
        if let Some(first) = chars.next() {
            let normalized_prefix = first.to_uppercase().collect::<String>() + chars.as_str();
            format!("{}:{}", normalized_prefix, rest.trim())
        } else {
            collapsed
        }
    } else {
        collapsed
    }
}

pub fn parse_source_list(input: &str) -> ParseResult {
    let mut titles = Vec::new();
    let mut warnings = Vec::new();
    let mut seen = BTreeSet::new();

    for (index, line) in input.lines().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() || is_comment_only(trimmed) {
            continue;
        }
        if is_unsupported_markup(trimmed) {
            warnings.push(format!(
                "Ignored unsupported source line {}: {}",
                index + 1,
                trimmed
            ));
            continue;
        }
        let normalized = normalize_title(trimmed);
        if normalized.is_empty() || !seen.insert(normalized.clone()) {
            continue;
        }
        titles.push(normalized);
    }

    ParseResult { titles, warnings }
}

fn is_comment_only(line: &str) -> bool {
    line.starts_with("<!--") && line.ends_with("-->")
}

fn is_unsupported_markup(line: &str) -> bool {
    line.starts_with('*')
        || line.starts_with('#')
        || line.starts_with("==")
        || line.contains("[[")
        || line.contains("{{")
        || line.contains("}}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_basic_titles() {
        assert_eq!(normalize_title(" Foo_bar "), "Foo bar");
        assert_eq!(normalize_title("user : Example "), "User:Example");
    }

    #[test]
    fn parses_strict_newline_titles() {
        let input = "Foo bar\n<!-- comment -->\nBaz_qux\n* ignored\n";
        let parsed = parse_source_list(input);
        assert_eq!(parsed.titles, vec!["Foo bar", "Baz qux"]);
        assert_eq!(parsed.warnings.len(), 1);
    }
}
