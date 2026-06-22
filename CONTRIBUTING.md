# Contributing

Thanks for your interest in Silo!

## Setup

```bash
git clone https://github.com/divyanshudhruv/silo.git
cd silo
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .
```

## Development

```bash
# Initialize a test repo
silo init /tmp/test-silo
cd /tmp/test-silo
silo commit "first snapshot"
silo log --oneline
```

## Tests

```bash
python tests/run_commands.py
```

On Windows: `python tests/run_commands.py`

## Before Submitting

- Run the full test suite (`python tests/run_commands.py`)
- Add tests for new functionality
- Update docs if you change CLI commands or config

## Code Style

- Follow existing patterns and conventions
- No comments in code (keep it self-documenting)
- Type hints on all function signatures
