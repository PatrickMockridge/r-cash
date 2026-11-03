//! Guard against reintroducing Rholang's removed built-in Decimal type (rholo issue #527).
//!
//! The node removed `GDecimal`, the `1.5d` literal and wire tag 35. R-Cash represents money
//! as 8-decimal integer base units; no Rholang term and no Rust term template may use the old
//! decimal syntax. This test scans the contract sources and the client's Rust sources.

use std::path::{Path, PathBuf};

fn walk(dir: &Path, suffix: &str, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            walk(&path, suffix, out);
        } else if path.extension().and_then(|ext| ext.to_str()) == Some(suffix) {
            out.push(path);
        }
    }
}

/// True for a Rholang decimal literal: digits, a dot, digits, `d`, then a non-identifier
/// boundary. This deliberately does not match Rust floats or dotted versions.
fn has_decimal_literal(text: &str) -> bool {
    let bytes = text.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        if !bytes[index].is_ascii_digit() {
            index += 1;
            continue;
        }
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
        }
        if bytes.get(index) != Some(&b'.') {
            continue;
        }
        index += 1;
        let fraction_start = index;
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
        }
        if index == fraction_start || bytes.get(index) != Some(&b'd') {
            continue;
        }
        let boundary = bytes
            .get(index + 1)
            .map(|next| !(next.is_ascii_alphanumeric() || *next == b'_'))
            .unwrap_or(true);
        if boundary {
            return true;
        }
    }
    false
}

#[test]
fn no_removed_decimal_type() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");

    for directory in ["contracts/src", "harness/scenarios"] {
        let mut files = Vec::new();
        walk(&root.join(directory), "rho", &mut files);
        for path in files {
            let text = std::fs::read_to_string(&path).expect("read Rholang source");
            assert!(
                !text.contains("GDecimal"),
                "{} uses the removed GDecimal type",
                path.display()
            );
            assert!(
                !has_decimal_literal(&text),
                "{} uses a removed Rholang decimal literal",
                path.display()
            );
        }
    }

    let mut files = Vec::new();
    walk(&root.join("crates"), "rs", &mut files);
    files.retain(|path| path.components().any(|part| part.as_os_str() == "src"));
    for path in files {
        let text = std::fs::read_to_string(&path).expect("read Rust source");
        assert!(
            !has_decimal_literal(&text),
            "{} uses a removed Rholang decimal literal",
            path.display()
        );
    }

    for directory in ["harness", "tools"] {
        let mut files = Vec::new();
        walk(&root.join(directory), "py", &mut files);
        for path in files {
            let text = std::fs::read_to_string(&path).expect("read Python source");
            assert!(
                !has_decimal_literal(&text),
                "{} uses a removed Rholang decimal literal",
                path.display()
            );
        }
    }
}
