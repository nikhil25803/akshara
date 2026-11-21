# Contributing to Akshara

Thank you for helping improve Akshara. Please read the
[Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Before opening an issue

- Search existing issues to avoid duplicates.
- Use the bug form for reproducible defects and the feature form for proposals.
- Do not disclose vulnerabilities in a public issue; follow
  [SECURITY.md](SECURITY.md) instead.
- Remove API keys, personal documents, and other sensitive data from logs and
  examples.

## Development setup

Requirements are Python 3.11+, [uv](https://docs.astral.sh/uv/), and Make.

```bash
git clone https://github.com/nikhil25803/akshara.git
```

```bash
cd akshara
```

```bash
uv sync --locked
```

```bash
cp .env.example .env
```

```bash
make generate-key
```

Save the generated value as `API_KEY` in `.env`.

```bash
make run
```

The full PaddlePaddle and llama.cpp CPU runtimes target Linux AMD64. Use the
Docker workflow from the README for integration testing on other platforms.

## Making changes

- Keep changes focused and consistent with the existing code style.
- Add or update tests for behavior changes.
- Update the README for public API, configuration, or workflow changes.
- Add a changelog entry for user-visible changes.
- Never commit secrets, model weights, generated distributions, or private test
  documents.

Run the complete local check before opening a pull request:

```bash
make check
```

## Pull requests

Describe the problem, the chosen solution, and how it was tested. Link related
issues and call out compatibility or deployment effects. Pull requests should
be small enough to review and must pass the repository checks.
