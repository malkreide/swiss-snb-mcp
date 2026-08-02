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
`ruff format` and the version-sync check. If the hook passes, that job passes.

Two details worth knowing:

- The hook runs Ruff at the version pinned in `.pre-commit-config.yaml`, in its
  own isolated environment — not whatever Ruff you happen to have installed.
  That pin and the `ruff==…` pin in `.github/workflows/ci.yml` must stay in
  sync; bump both together.
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
ruff check src/ tests/
ruff format src/ tests/
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
