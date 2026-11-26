#!/usr/bin/env python3
"""Run every case through `packaging` (the reference) and each target, explain every difference.

    python run.py            # writes results/*.json and RESULTS.md, exits 1 on unexplained differences

A difference is "explained" when a rule in RULES matches it. Each rule names its category, whether
the difference is intended, and the source that says so. A difference no rule matches is new: it
is either a regression in a target or something worth reporting upstream.
"""

import itertools
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import packaging
from packaging.markers import InvalidMarker, Marker, UndefinedComparison
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

import cases

ROOT = Path(__file__).resolve().parent
PINS = json.loads((ROOT / "pins.json").read_text())
UV_BIN = ROOT / "targets/uv/target/release/uv-target"
VERSION_KEYS = ("python_version", "python_full_version", "implementation_version")


# ----------------------------------------------------------------------------- tasks
def build_tasks():
    versions = cases.VERSIONS + cases.fuzz_versions(4000)
    valid = sorted({v for v in versions if _ok(lambda: Version(v))} | set(cases.PROBE_VERSIONS))
    tasks = [{"op": "version", "s": v} for v in versions]
    tasks += [{"op": "compare", "a": a, "b": b} for a, b in itertools.combinations(valid[:150], 2)]
    tasks += [{"op": "spec", "s": s} for s in cases.SPECS]
    tasks += [{"op": "contains", "spec": s, "v": v} for s in cases.SPECS for v in cases.PROBE_VERSIONS]
    tasks += [{"op": "marker", "m": m} for m in cases.MARKERS]
    return tasks


def _ok(fn):
    try:
        fn()
        return True
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------------------- reference
def reference(t):
    op = t["op"]
    try:
        if op == "version":
            return {"ok": True, "value": str(Version(t["s"]))}
        if op == "compare":
            a, b = Version(t["a"]), Version(t["b"])
            return {"ok": True, "value": (a > b) - (a < b)}
        if op == "spec":
            return {"ok": True, "value": sorted(str(SpecifierSet(t["s"])).split(","))}
        if op == "contains":
            return {"ok": True, "value": SpecifierSet(t["spec"]).contains(Version(t["v"]), prereleases=True)}
        if op == "marker":
            return {"ok": True, "value": Marker(t["m"]).evaluate(cases.ENV)}
    except (InvalidVersion, InvalidSpecifier, InvalidMarker):
        return {"ok": False, "error": "invalid"}
    except UndefinedComparison:
        return {"ok": False, "error": "undefined comparison"}
    raise ValueError(op)


# ----------------------------------------------------------------------------- targets
def run_uv(tasks):
    proc = subprocess.run([str(UV_BIN)], input="\n".join(json.dumps(t) for t in tasks) + "\n",
                          capture_output=True, text=True, check=True)
    out = []
    for t, line in zip(tasks, proc.stdout.splitlines()):
        r = json.loads(line)
        if r.get("panic"):
            out.append({"ok": False, "error": "PANIC"})
        elif not r["ok"]:
            out.append({"ok": False, "error": r.get("err", "invalid")})
        else:
            value = r.get("norm", r.get("cmp", r.get("contains", r.get("eval"))))
            if t["op"] == "spec":
                value = sorted(value.replace(" ", "").split(",")) if value else [""]
            out.append({"ok": True, "value": value})
    return out


def run_poetry(tasks):
    from poetry.core.constraints.version import Version as PV
    from poetry.core.constraints.version import parse_constraint
    from poetry.core.version.markers import parse_marker

    out = []
    for t in tasks:
        op = t["op"]
        try:
            if op == "version":
                value = PV.parse(t["s"]).to_string()
            elif op == "compare":
                a, b = PV.parse(t["a"]), PV.parse(t["b"])
                value = (a > b) - (a < b)
            elif op == "spec":
                parse_constraint(t["s"])
                value = None  # poetry has no PEP 440 rendering of a constraint; only acceptance is compared
            elif op == "contains":
                value = parse_constraint(t["spec"]).allows(PV.parse(t["v"]))
            else:
                value = parse_marker(t["m"]).validate(cases.ENV)
            out.append({"ok": True, "value": value})
        except Exception as e:  # noqa: BLE001
            out.append({"ok": False, "error": type(e).__name__})
    return out


TARGETS = {
    "uv": {"run": run_uv, "label": f"uv @ {PINS['uv'][:7]}", "crates": "uv-pep440, uv-pep508"},
    "poetry-core": {"run": run_poetry, "label": f"poetry-core {PINS['poetry-core']}", "crates": "poetry.core"},
}


# ----------------------------------------------------------------------------- rules
def marker_parts(m):
    """(key, operator, value, reversed) for a single comparison, else None."""
    keys = "|".join(sorted(["python_version", "python_full_version", "implementation_version", "platform_release",
                            "platform_version", "platform_machine", "sys_platform", "os_name", "platform_system",
                            "implementation_name", "extra"], key=len, reverse=True))
    q = r"""["']([^"']*)["']"""
    ops = r"(===|==|!=|~=|>=|<=|>|<|not in|in)"
    if mt := re.fullmatch(rf"\s*({keys})\s*{ops}\s*{q}\s*", m):
        return mt[1], mt[2], mt[3], False
    if mt := re.fullmatch(rf"\s*{q}\s*{ops}\s*({keys})\s*", m):
        return mt[3], mt[2], mt[1], True
    return None


def invalid_version_comparison(m):
    p = marker_parts(m)
    if not p or p[0] not in VERSION_KEYS or p[1] in ("in", "not in"):
        return False
    return not _ok(lambda: SpecifierSet(f"{p[1]}{p[2]}"))


def has_extra_segments(value):
    try:
        v = Version(value)
    except InvalidVersion:
        return False
    return bool(v.epoch or v.pre or v.post is not None or v.dev is not None or v.local)


def text_of(t):
    return " ".join(str(v) for k, v in t.items() if k != "op")


SRC_UV = f"https://github.com/astral-sh/uv/blob/{PINS['uv']}"
RULES = [
    # --- uv
    dict(target="uv", id="uv-whitespace", status="stricter",
         title="Leading or trailing whitespace around a version is rejected",
         why="`Version::from_str` does not strip whitespace; packaging does (PEP 440 says it should be ignored). "
             "uv's callers trim input before parsing, so this only shows when the crate is called directly.",
         source=f"{SRC_UV}/crates/uv-pep440/src/version.rs",
         match=lambda t, r, g: t["op"] in ("version", "compare") and text_of(t) != text_of(t).strip()
         or (t["op"] == "compare" and not g["ok"])),
    dict(target="uv", id="uv-u64", status="intended",
         title="Release numbers above 2^64 - 2 are rejected",
         why="Release segments are stored as u64; the error says so explicitly.",
         source=f"{SRC_UV}/crates/uv-pep440/src/version.rs",
         match=lambda t, r, g: not g["ok"] and "exceeds" in g.get("error", "")),
    dict(target="uv", id="uv-arbitrary-equality", status="intended",
         title="`===` compares parsed versions, not strings, and needs a valid version",
         why="Documented in the code: 'This isn't standards-compliant, but it's consistent with the resolver'.",
         source=f"{SRC_UV}/crates/uv-pep440/src/version_specifier.rs#L668-L677",
         match=lambda t, r, g: "===" in text_of(t)),
    dict(target="*", id="empty-clause", status="stricter",
         title="An empty specifier or empty clause (`\"\"`, `,`, a trailing comma) is rejected",
         why="The PEP 440 grammar has no empty clause; packaging silently drops it.",
         source="https://packaging.python.org/en/latest/specifications/version-specifiers/",
         match=lambda t, r, g: t["op"] in ("spec", "contains")
         and re.search(r"(^\s*,|,\s*$|^\s*$)", t.get("s", t.get("spec", ""))) is not None),
    dict(target="uv", id="spelling", status="cosmetic",
         title="packaging keeps the original spelling of a specifier's version",
         why="`str(SpecifierSet('==v1.0'))` is `==v1.0`; uv renders the parsed version `==1.0`. Same set.",
         source="https://packaging.pypa.io/en/stable/specifiers.html",
         match=lambda t, r, g: t["op"] == "spec" and r["ok"] and g["ok"] and [x.replace("v", "") for x in r["value"]] == g["value"]),
    dict(target="uv", id="uv-invalid-marker-ignored", status="intended",
         title="A marker comparing a version key with something that is not a valid specifier evaluates to true",
         why="The parser reports 'Expected PEP 440 version ... will be ignored' and drops the expression. "
             "packaging falls back to a string comparison (usually false) or raises.",
         source=f"{SRC_UV}/crates/uv-pep508/src/marker/parse.rs#L441-L489",
         match=lambda t, r, g: t["op"] == "marker" and invalid_version_comparison(t["m"])),
    dict(target="uv", id="uv-release-only", status="intended",
         title="Python version markers compare only the release part (epoch, pre, post, dev, local ignored)",
         why="Documented: 'uv truncates the candidate version to the major, minor, and patch components'. "
             "The marker algebra calls `only_release()` and has a `release_only` test.",
         source=f"{SRC_UV}/docs/pip/compatibility.md#requires-python-specifiers",
         match=lambda t, r, g: t["op"] == "marker" and (p := marker_parts(t["m"])) is not None
         and p[0] in VERSION_KEYS and has_extra_segments(p[2])),
    # --- shared
    dict(target="*", id="in-is-a-version-list", status="spec-question",
         title="`in` with a version key is a whitespace-separated list of versions, not a substring test",
         why="PEP 508 defines `in` as Python string containment, which packaging follows ('3.1' in '3.12' is true). "
             "uv and poetry-core read the right side as a list of versions. Discussed upstream.",
         source="https://github.com/pypa/packaging/issues/552",
         match=lambda t, r, g: t["op"] == "marker" and (p := marker_parts(t["m"])) is not None
         and p[1] in ("in", "not in") and (p[0] in VERSION_KEYS or p[0] == "platform_release")),
    dict(target="*", id="string-fallback", status="spec-question",
         title="Ordered comparison on a non-version value (`platform_release >= \"6.0\"` on `6.8.0-45-generic`)",
         why="PEP 508 says to fall back to a string comparison (true here). packaging returns false for an "
             "invalid version since 22.0; uv and poetry-core compare. Long-standing upstream discussion.",
         source="https://github.com/pypa/packaging/issues/774",
         match=lambda t, r, g: t["op"] == "marker" and (p := marker_parts(t["m"])) is not None
         and p[0] in ("platform_release", "platform_version") and p[1] not in ("==", "!=", "in", "not in")),
    # --- poetry-core
    dict(target="poetry-core", id="poetry-uppercase-tags", status="bug (reported)",
         title="Uppercase pre/post/dev tags are not lowercased (`1.0RC1` sorts before `1.0a1`)",
         why="`ReleaseTag.__post_init__` looks the phase up in its alias table without lowercasing it first.",
         source="https://github.com/python-poetry/poetry-core/pull/1000",
         match=lambda t, r, g: t["op"] in ("version", "compare", "contains")
         and re.search(r"(?<![+.\w])\d*[.\-_]?(RC|Rc|C|ALPHA|Alpha|BETA|PRE|PREVIEW|DEV|POST|REV|R)\d*", text_of(t)) is not None),
    dict(target="poetry-core", id="poetry-constraint-syntax", status="intended",
         title="Poetry's own constraint syntax is accepted (`~1.0`, `=1.0`, a bare `1.0`, local versions with `>=`)",
         why="`parse_constraint` parses Poetry's dependency syntax, a superset of PEP 440 specifiers.",
         source="https://python-poetry.org/docs/dependency-specification/",
         match=lambda t, r, g: t["op"] in ("spec", "contains") and not r["ok"] and g["ok"]),
    dict(target="poetry-core", id="poetry-string-ordering", status="bug (same root cause as #1002)",
         title="Ordered comparisons on string markers (`os_name >= \"posix\"`) never match",
         why="The generic string constraint has no ordered operators; PEP 508 says to compare as Python strings.",
         source="https://github.com/python-poetry/poetry-core/pull/1002",
         match=lambda t, r, g: t["op"] == "marker" and (p := marker_parts(t["m"])) is not None
         and p[0] not in VERSION_KEYS + ("platform_release",) and p[1] in (">", ">=", "<", "<=", "~=")),
    dict(target="poetry-core", id="poetry-local-zeros", status="cosmetic",
         title="Numeric local segments keep their leading zeros in the text (`1.0+01`)",
         why="Comparison is unaffected (`1.0+01 == 1.0+1`); only the rendered string differs from packaging's `1.0+1`.",
         source="https://packaging.python.org/en/latest/specifications/version-specifiers/#local-version-identifiers",
         match=lambda t, r, g: t["op"] == "version" and "+" in t["s"] and r["ok"] and g["ok"]
         and Version(t["s"]) == Version(g["value"])),
    dict(target="poetry-core", id="poetry-arbitrary-equality", status="unsupported",
         title="`===` is not supported",
         why="poetry-core's constraint parser has no arbitrary-equality operator.",
         source="https://github.com/python-poetry/poetry-core/tree/main/src/poetry/core/constraints/version",
         match=lambda t, r, g: "===" in text_of(t)),
    dict(target="poetry-core", id="poetry-implementation-version", status="bug (reported)",
         title="`implementation_version` is compared as a string, so `>=`, `<`, `>` never match",
         why="poetry-core treats only python_version / python_full_version / platform_release as versions.",
         source="https://github.com/python-poetry/poetry-core/pull/1002",
         match=lambda t, r, g: t["op"] == "marker" and "implementation_version" in t["m"]),
    dict(target="poetry-core", id="poetry-reversed-operands", status="bug (reported)",
         title="A marker with the string on the left (`\"linux\" == sys_platform`) fails to parse",
         why="The grammar accepts it, but `_compact_markers` only handles swapped operands for `in` / `not in`.",
         source="https://github.com/python-poetry/poetry/issues/11285",
         match=lambda t, r, g: t["op"] == "marker" and (p := marker_parts(t["m"])) is not None and p[3]
         and p[1] not in ("in", "not in")),
    dict(target="poetry-core", id="poetry-invalid-marker", status="stricter",
         title="A marker comparing a version key with an invalid version is rejected",
         why="poetry-core raises InvalidMarkerError where packaging falls back to a string comparison or raises.",
         source="https://github.com/python-poetry/poetry-core/blob/main/src/poetry/core/version/markers.py",
         match=lambda t, r, g: t["op"] == "marker" and invalid_version_comparison(t["m"])),
]


def explain(target, t, r, g):
    for rule in RULES:
        if rule["target"] in (target, "*") and rule["match"](t, r, g):
            return rule["id"]
    return None


def same(op, r, g):
    if r["ok"] != g["ok"]:
        return False
    if not r["ok"]:
        return True
    if op == "spec" and g["value"] is None:
        return True
    return r["value"] == g["value"]


# ----------------------------------------------------------------------------- report
def main():
    tasks = build_tasks()
    refs = [reference(t) for t in tasks]
    (ROOT / "results").mkdir(exist_ok=True)
    summary = {}
    for name, target in TARGETS.items():
        got = target["run"](tasks)
        diffs = defaultdict(list)
        for t, r, g in zip(tasks, refs, got):
            if same(t["op"], r, g):
                continue
            diffs[explain(name, t, r, g) or "UNEXPLAINED"].append({"input": t, "packaging": r, name: g})
        summary[name] = diffs
        (ROOT / "results" / f"{name}.json").write_text(json.dumps(diffs, ensure_ascii=False, indent=1) + "\n")

    write_report(tasks, summary)
    unexplained = sum(len(d.get("UNEXPLAINED", [])) for d in summary.values())
    print((ROOT / "RESULTS.md").read_text())
    return 1 if unexplained else 0


def write_report(tasks, summary):
    by_op = Counter(t["op"] for t in tasks)
    rules = {r["id"]: r for r in RULES}
    lines = ["# Results", "",
             f"Reference: `packaging` {packaging.__version__}. "
             + ", ".join(f"{TARGETS[n]['label']}" for n in summary) + ".", "",
             f"{len(tasks):,} cases: " + ", ".join(f"{n:,} {op}" for op, n in by_op.items()) + ".", "",
             "Generated by `./run.sh`; do not edit by hand.", ""]
    for name, diffs in summary.items():
        total = sum(len(v) for v in diffs.values())
        lines += [f"## {TARGETS[name]['label']}", "",
                  f"{len(tasks) - total:,} of {len(tasks):,} cases agree with packaging. "
                  f"{total:,} differ, in {len(diffs)} categor{'y' if len(diffs) == 1 else 'ies'}:", "",
                  "| Category | Status | Cases | Example | Source |", "|---|---|---|---|---|"]
        for cid, items in sorted(diffs.items(), key=lambda kv: (kv[0] == "UNEXPLAINED", -len(kv[1]))):
            ex = items[0]
            example = f"`{text_of(ex['input'])}`: packaging {_fmt(ex['packaging'])}, {name} {_fmt(ex[name])}"
            if cid == "UNEXPLAINED":
                lines.append(f"| **Unexplained** | ⚠ new | {len(items)} | {example} | — |")
            else:
                rule = rules[cid]
                lines.append(f"| {rule['title']} | {rule['status']} | {len(items)} | {example} | [source]({rule['source']}) |")
        lines.append("")
        for cid in diffs:
            if cid != "UNEXPLAINED":
                lines.append(f"- **{rules[cid]['title']}.** {rules[cid]['why']}")
        lines.append("")
    (ROOT / "RESULTS.md").write_text("\n".join(lines))


def _fmt(o):
    if not o["ok"]:
        return f"rejects ({o.get('error', '')[:40]})"
    v = o["value"]
    return f"`{v}`" if not isinstance(v, list) else "`" + ",".join(v) + "`"


if __name__ == "__main__":
    sys.exit(main())
