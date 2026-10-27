<div align="center">

# Akshara | अक्षर

**From text to understanding.**

</div>

Akshara is an open-source, local-first document intelligence
engine built with Python. It aims to turn images and PDFs into
structured data and useful answers using OCR and optional LLMs.

## Features

- OCR-first architecture
- Optional LLM processing
- Configurable through environment variables
- HTTP API powered by FastAPI
- CPU-first inference configuration
- API-key protected OCR for JPEG, PNG, and PDF uploads

## Getting started

Install the cross-platform development dependencies:

```bash
uv sync
```

PaddlePaddle inference is supported through the Linux container. Copy the example configuration and generate a local key without downloading any extra tool:

```bash
cp .env.example .env
make generate-key
```

Save the printed value as `API_KEY` in `.env`. The generator uses Python's standard-library `secrets` module and is only a convenience; you may use any strong key of at least 32 characters.

Build and run the CPU image (Apple Silicon uses Docker's amd64 emulation):

```bash
make docker-build
make docker-run
```

The first OCR request for each language downloads its model. The `akshara-models` Docker volume keeps those models between containers.

## OCR API

`POST /v1/ocr` accepts one `file` field as `multipart/form-data`. JPEG, PNG, and PDF content is supported. Filenames and client MIME declarations are not trusted.

```bash
curl -X POST http://localhost:8000/v1/ocr \
  -H "api_key: $API_KEY" \
  -F "file=@document.pdf"
```

Select an enabled language and optional details with query parameters:

```bash
curl -X POST "http://localhost:8000/v1/ocr?language=hi&page_details=true&extraction_source=true&coordinates=true" \
  -H "api_key: $API_KEY" \
  -F "file=@document.png"
```

The compact response contains `text`, `language`, detected `mime_type`, `page_count`, and `warnings`. When details are requested, `pages` contains the selected page text/source and normalized `0..1` coordinates. PDFs use embedded text when available and OCR only for scanned pages.

Every endpoint except `/` and `/health` requires the `api_key` header. Typical failures are `401` for authentication, `400` for malformed documents, `413` for configured limits, `415` for unsupported or spoofed content, `429` when OCR is busy, and `503` when PaddleOCR is unavailable.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_KEY` | required | Strong key of at least 32 characters |
| `OCR_LANGUAGES` | `en,hi` | Comma-separated language allowlist; the first is the request default |
| `OCR_MAX_CONCURRENT_REQUESTS` | `1` | Maximum simultaneous OCR operations |
| `MAX_FILE_SIZE_MB` | `25` | Maximum uploaded file size |
| `MAX_PDF_PAGES` | `50` | Maximum pages per PDF |
| `MAX_IMAGE_PIXELS` | `25000000` | Maximum pixels per image or rendered PDF page |

`/health` reports `paddleocr: true` when the inference runtime is available, otherwise it reports a degraded state. It does not download models.

<details>
<summary>Supported OCR language codes</summary>

Hindi uses `hi` (not `hn`). Each language used by a request can download and retain another model.

`abq`, `af`, `ang`, `ar`, `ava`, `az`, `be`, `bg`, `bgc`, `bh`, `bho`, `bs`, `ch`, `che`, `chinese_cht`, `cs`, `cy`, `da`, `dar`, `de`, `en`, `es`, `et`, `fa`, `fr`, `ga`, `gom`, `hi`, `hr`, `hu`, `id`, `inh`, `is`, `it`, `japan`, `ka`, `kbd`, `korean`, `ku`, `la`, `lbe`, `lez`, `lt`, `lv`, `mah`, `mai`, `mi`, `mn`, `mr`, `ms`, `mt`, `ne`, `new`, `nl`, `no`, `oc`, `pi`, `pl`, `pt`, `ro`, `rs_cyrillic`, `rs_latin`, `ru`, `sa`, `sck`, `sk`, `sl`, `sq`, `sv`, `sw`, `tab`, `ta`, `te`, `tl`, `tr`, `ug`, `uk`, `ur`, `uz`, `vi`

</details>
