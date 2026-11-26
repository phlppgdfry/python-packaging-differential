# Python packaging, differentially tested

pip, uv and Poetry all have to agree on what `1.0rc1`, `>=1.0,!=1.5.*` and `python_version < "3.13"` mean. pip uses the reference library [`packaging`](https://github.com/pypa/packaging). **uv** reimplements the rules in Rust (`uv-pep440`, `uv-pep508`), and **Poetry** has its own implementation in `poetry-core`.

This repository runs **15,455 inputs** through all three and **explains every difference**. Each difference is matched to a rule that says whether it is intended, a question about the specification, or a bug, and links the source that says so. A difference that no rule explains fails the run. The weekly CI also re-runs everything against uv `main` and the latest `packaging` and `poetry-core`, so a behaviour change in any of them shows up as a red build.

> Unofficial. Not affiliated with Astral, the Poetry project or the PyPA.

**→ [RESULTS.md](RESULTS.md)** has the full tables.

## Findings

| | uv (`e3e7c1e`) | poetry-core 2.5.0 |
|---|---|---|
| Cases that agree with `packaging` 26.4 | 15,211 of 15,455 | 15,128 of 15,455 |
| Differences, explained | 244 in 9 categories | 327 in 11 categories |
| Bugs | **none** | **4** (1 found here and reported, 3 already reported or open as a PR) |

**uv:** every difference is deliberate and written down. It ignores invalid marker versions with a warning, compares Python versions on the release part only ([documented](https://github.com/astral-sh/uv/blob/e3e7c1eacb980339352a5ad69affcd3b6c206c92/docs/pip/compatibility.md#requires-python-specifiers)), makes `===` compare parsed versions ([commented in the code](https://github.com/astral-sh/uv/blob/e3e7c1eacb980339352a5ad69affcd3b6c206c92/crates/uv-pep440/src/version_specifier.rs#L668-L677)), and is stricter about whitespace and empty clauses.

**poetry-core:**

| Bug | Status |
|---|---|
| A marker with the value on the left (`"linux" == sys_platform`, `"3.8" < python_version`) raises `InvalidMarkerError`, although PEP 508 allows it | **Found here.** Reported in [python-poetry/poetry#11285](https://github.com/python-poetry/poetry/issues/11285), fix in [poetry-core#1006](https://github.com/python-poetry/poetry-core/pull/1006) |
| Uppercase pre/post/dev tags are not lowercased, so `1.0RC1` sorts before `1.0a1` | Already reported: poetry#11235, fix in poetry-core#1000 |
| `implementation_version` is compared as a string, so `>=`/`<` never match | Already open: poetry-core#1002 |
| Ordered comparisons on string markers (`os_name >= "posix"`) never match | Same root cause as poetry-core#1002 |

**Shared, specification questions:** `in` with a version key (`python_version in "3.12.4"`) is substring containment in the spec and in `packaging`, but uv and Poetry read it as a list of versions ([pypa/packaging#552](https://github.com/pypa/packaging/issues/552)). Ordered comparisons on non-version strings such as a Linux kernel `platform_release` fall back to string comparison in the spec, while `packaging` returns false ([pypa/packaging#774](https://github.com/pypa/packaging/issues/774)).

## How it works

```
cases.py ──► run.py ──► packaging (reference)
                   ├──► uv: targets/uv, a 60-line Rust binary on uv's own crates, built from the pinned commit
                   └──► poetry-core: called in-process
             ──► every difference matched against RULES ──► results/*.json + RESULTS.md (exit 1 if unexplained)
```

- **Inputs:** hand-picked edge cases from the version and dependency-specifier specs (epochs, local versions, implicit post-releases, wildcards, `~=`, `===`, swapped marker operands, whitespace, Unicode digits, 64-bit overflow), plus 4,000 seeded random versions. The comparisons cover every pair of the first 150 valid versions.
- **Operations:** parse and normalize a version, compare two versions, parse a specifier set, test a version against a specifier, and evaluate a marker against a fixed CPython 3.12.4 Linux environment.
- **Rules:** each rule in `run.py` has a status (`intended`, `stricter`, `cosmetic`, `spec-question`, `unsupported`, `bug (reported)`) and a link to the code, documentation or issue that backs it.

## Run it

Needs Rust, [uv](https://docs.astral.sh/uv/) and git.

```sh
./run.sh   # fetches uv at the pinned commit, builds the target, installs the pinned packages, runs
```

Versions are pinned in `pins.json`.

## License

MIT
