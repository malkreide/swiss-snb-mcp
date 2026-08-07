# Contributing to swiss-snb-mcp

[🇩🇪 Deutsche Version](CONTRIBUTING.de.md)

Thank you for your interest in contributing to `swiss-snb-mcp`! This project is part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide).

---

## Ways to Contribute

### Report a Bug

Open a [GitHub Issue](https://github.com/malkreide/swiss-snb-mcp/issues) and include:

- A clear description of the problem
- Steps to reproduce
- Expected vs. actual behaviour
- Python version and OS

### Suggest a New SNB Cube

The SNB data portal contains many cubes beyond the 8 currently verified in this server. If you discover a useful cube ID:

1. Open an issue with the title `[Cube] <cube_id>: <short description>`
2. Include the cube ID, a sample API call, and a description of the data it contains
3. Ideally, verify it against the live API before submitting

### Improve Documentation

Typos, unclear explanations, or missing examples are always welcome as pull requests — no issue needed.

### Contribute Code

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Follow the code style (Ruff for linting/formatting)
4. Add or update tests in `tests/`
5. Run the test suite before submitting: `PYTHONPATH=src pytest tests/ -m "not live"`
6. Submit a pull request with a clear description of your changes

---

## Development Setup

```bash
git clone https://github.com/malkreide/swiss-snb-mcp.git
cd swiss-snb-mcp
pip install -e ".[dev]"
pre-commit install
```

**Pre-commit hook:**

`pre-commit install` is a one-off step per clone. It wires up the hooks in
`.pre-commit-config.yaml`, which mirror the `lint` job in CI: `ruff check`,
`ruff format`, the version-sync check and the Ruff-pin-sync check. If the hook
passes, that job passes.

Two details worth knowing:

- The hook runs Ruff at the version pinned in `.pre-commit-config.yaml`, in its
  own isolated environment — not whatever Ruff you happen to have installed.
  That pin and the `ruff==…` pin in `.github/workflows/ci.yml` must stay in
  sync; bump both together. `scripts/check_ruff_pin.py` enforces this, in the
  hook and in CI.
- `ruff format` reformats your files in place and then fails the commit. Stage
  the reformatted files and commit again. `ruff check` only reports, matching
  what CI does.

To run the hooks over the whole tree without committing:

```bash
pre-commit run --all-files
```

**Run tests:**

```bash
# Unit tests (no network required)
PYTHONPATH=src pytest tests/ -m "not live"

# Integration tests (live SNB API)
PYTHONPATH=src pytest tests/ -m "live"
```

**Lint and format:**

```bash
ruff check src/ tests/ scripts/
ruff format src/ tests/ scripts/
```

---

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | When to use |
|---|---|
| `feat:` | New tool or new SNB dataset |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `test:` | Adding or updating tests |
| `refactor:` | Code restructuring without behaviour change |
| `chore:` | Build, dependencies, CI |

---

## Code of Conduct

Be respectful and constructive. This is a small open-source project maintained in spare time — patience is appreciated.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## The nightly live run: who sees a red result

**Cadence:** every night at 03:17 UTC, plus on demand via *Actions → CI → Run
workflow*. The `live` job never runs on a pull request — a `data.snb.ch` outage
must not hold the mainline build hostage.

That job has run since this repository was written. What it lacked was the part
below: **nobody saw a red result.** A scheduled run whose outcome only lands as a
red entry in the Actions tab is a more expensive way of not running — red crons
stop being looked at in the second week.

**Who sees it now:** a red night opens an issue titled `Live-Tests gegen
data.snb.ch rot …` with the `upstream` label, and comments on the existing one
instead of opening a second. With a *daily* cron that is not a nicety; it is the
difference between one thread and thirty issues a month. A run that goes green
again closes it.

**Three answers, not two.** `scripts/classify_live_scenarios.py` reads the
scenario runners' own summary line rather than the exit code alone, and
separates `clear` (ran, all passed), `finding` (ran, something fell) and
`unknown` (did not run — install failed, timeout, import error, or **zero
scenarios registered**). That last one matters: `main()` returns `FAILED == 0`,
which with no scenarios registered is `True` — a green run that checked nothing.
An `unknown` never closes an issue: closing would claim a comparison that never
happened.

**A red live run does not necessarily mean *our* bug.** It means the contract
with the SNB has changed, or the source is down. Both belong seen; only the first
belongs fixed. Please read the run before disabling the job — the live scenarios
are the only tests here that can contradict a wrong assumption about
`data.snb.ch`, because every other test asserts against a fixture written from
the same assumption.
