# Changelog

All notable changes to Akshara are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.1] - 2026-10-27

### Added

- Authenticated OCR API for JPEG, PNG, and PDF documents.
- Embedded PDF text extraction with PaddleOCR fallback for scanned pages.
- Environment-controlled multilingual OCR and processing limits.
- MIME, file-size, page-count, pixel-count, and concurrency protections.
- CPU Docker image with a persistent cache for lazily downloaded models.
- Cross-platform tests and Docker health checks in GitHub Actions.

[Unreleased]: https://github.com/nikhil25803/akshara/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/nikhil25803/akshara/releases/tag/v0.0.1
