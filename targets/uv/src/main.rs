//! Reads one JSON task per line on stdin and writes one JSON result per line on stdout,
//! using uv's own uv-pep440 / uv-pep508 crates.
use std::io::{BufRead, Write};
use std::str::FromStr;

use serde_json::{Value, json};
use uv_pep440::{Version, VersionSpecifiers};
use uv_pep508::{MarkerEnvironment, MarkerEnvironmentBuilder, MarkerTree};

fn env() -> MarkerEnvironment {
    MarkerEnvironment::try_from(MarkerEnvironmentBuilder {
        implementation_name: "cpython",
        implementation_version: "3.12.4",
        os_name: "posix",
        platform_machine: "x86_64",
        platform_python_implementation: "CPython",
        platform_release: "6.8.0-45-generic",
        platform_system: "Linux",
        platform_version: "#45-Ubuntu SMP PREEMPT_DYNAMIC",
        python_full_version: "3.12.4",
        python_version: "3.12",
        sys_platform: "linux",
    })
    .unwrap()
}

fn main() {
    let env = env();
    let stdin = std::io::stdin();
    let mut out = std::io::BufWriter::new(std::io::stdout());
    for line in stdin.lock().lines() {
        let task: Value = serde_json::from_str(&line.unwrap()).unwrap();
        let s = |k: &str| task[k].as_str().unwrap().to_string();
        let result = std::panic::catch_unwind(|| match task["op"].as_str().unwrap() {
            "version" => match Version::from_str(&s("s")) {
                Ok(v) => json!({"ok": true, "norm": v.to_string()}),
                Err(e) => json!({"ok": false, "err": e.to_string()}),
            },
            "compare" => match (Version::from_str(&s("a")), Version::from_str(&s("b"))) {
                (Ok(a), Ok(b)) => json!({"ok": true, "cmp": a.cmp(&b) as i8}),
                _ => json!({"ok": false}),
            },
            "spec" => match VersionSpecifiers::from_str(&s("s")) {
                Ok(v) => json!({"ok": true, "norm": v.to_string()}),
                Err(e) => json!({"ok": false, "err": e.to_string()}),
            },
            "contains" => match (VersionSpecifiers::from_str(&s("spec")), Version::from_str(&s("v"))) {
                (Ok(spec), Ok(v)) => json!({"ok": true, "contains": spec.contains(&v)}),
                _ => json!({"ok": false}),
            },
            "marker" => match MarkerTree::from_str(&s("m")) {
                Ok(m) => json!({"ok": true, "eval": m.evaluate(&env, &[])}),
                Err(e) => json!({"ok": false, "err": e.to_string().lines().next().unwrap_or("").to_string()}),
            },
            op => json!({"ok": false, "err": format!("unknown op {op}")}),
        });
        let result = result.unwrap_or_else(|_| json!({"ok": false, "panic": true}));
        writeln!(out, "{result}").unwrap();
    }
}
