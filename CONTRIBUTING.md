# Contributing to The Chak Chak Mage

Thanks for your interest in contributing! This project is an interactive album platform built by a human + AI team.

## How to Contribute

### Reporting Bugs

- Open an [issue](https://github.com/az-dev-me/chak-chak-mage/issues/new?template=bug_report.md)
- Include browser, OS, and steps to reproduce
- Screenshots or console errors help a lot

### Suggesting Features

- Open an [issue](https://github.com/az-dev-me/chak-chak-mage/issues/new?template=feature_request.md) with the feature request template
- Describe the use case, not just the solution

### Pull Requests

1. Fork the repo and create a branch from `master`
2. Make your changes
3. Test locally with `python -m http.server 8080`
4. Open a PR with a clear description of what changed and why

### Development Setup

```bash
# Clone the repo
git clone https://github.com/az-dev-me/chak-chak-mage.git
cd chak-chak-mage

# Serve locally (no build step needed)
python -m http.server 8080
# Open http://localhost:8080
```

The frontend is pure vanilla HTML/CSS/JS with no build tools or dependencies.

### Pipeline Development

The Python pipeline (`chak`) handles audio alignment, image generation, and data export:

```bash
pip install -e .
chak --help
```

See [docs/NEW_ALBUM_GUIDE.md](docs/NEW_ALBUM_GUIDE.md) for the full pipeline workflow.

## Code Style

- Frontend: vanilla JS, no frameworks, no transpilation
- Python: standard formatting, type hints where helpful
- Keep it simple -- no over-engineering

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
