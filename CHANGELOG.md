# Changelog

All notable changes to Akshara are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.4] - 2026-11-21

### Added

- Grounded, one-shot questions against uploaded documents through llama.cpp.
- Real-model document question coverage in a standalone OCR Ask GitHub Actions workflow.

## [0.0.3] - 2026-11-21

### Added

- Caller-defined JSON Schema extraction through a local llama.cpp model.
- Real-model schema extraction coverage in the OCR GitHub Actions workflow.
- Contribution, security, conduct, issue, and pull-request guidance.

### Changed

- Added Docker-first quick-start and real OCR and schema response examples to the README.

## [0.0.2] - 2026-11-20

### Added

- End-to-end GitHub Actions checks for health and JPEG, PNG, and PDF OCR.
- OCR response details, validation metrics, and request timings in CI output.

## [0.0.1] - 2026-10-27

### Added

- Authenticated OCR API for JPEG, PNG, and PDF documents.
- Embedded PDF text extraction with PaddleOCR fallback for scanned pages.
- Environment-controlled multilingual OCR and processing limits.
- MIME, file-size, page-count, pixel-count, and concurrency protections.
- CPU Docker image with a persistent cache for lazily downloaded models.
- Cross-platform tests and Docker health checks in GitHub Actions.

[Unreleased]: https://github.com/nikhil25803/akshara/compare/v0.0.4...HEAD
[0.0.4]: https://github.com/nikhil25803/akshara/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/nikhil25803/akshara/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/nikhil25803/akshara/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/nikhil25803/akshara/releases/tag/v0.0.1
