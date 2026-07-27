"""Bounded text-layer extraction for official Huatai Futures PDF attachments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
import logging
import multiprocessing
from multiprocessing.connection import Connection
import re
import time
from typing import Callable, Protocol
from unicodedata import normalize
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


HTFC_DOMAINS = frozenset({"htfc.com", "www.htfc.com"})
PDF_MEDIA_TYPE = "application/pdf"
PDF_SIGNATURE = b"%PDF-"
DEFAULT_USER_AGENT = "FuturesIntelligenceAssistant/0.1"


@dataclass(frozen=True)
class HuataiPdfAttachment:
    """Explicit listing context for one already-classified official PDF URL."""

    url: str
    listing_title: str | None = None
    publication_date: date | None = None
    report_type: str | None = None
    report_author: str | None = None


@dataclass(frozen=True)
class HuataiPdfDownloadLimits:
    """Strict network limits for one official PDF attachment."""

    socket_timeout_seconds: float = 10.0
    download_deadline_seconds: float = 30.0
    max_response_bytes: int = 20 * 1024 * 1024
    max_redirects: int = 3
    max_selected_pdfs: int = 3

    def __post_init__(self) -> None:
        if self.socket_timeout_seconds <= 0 or self.download_deadline_seconds <= 0:
            raise ValueError("PDF download timeouts must be positive")
        if self.max_response_bytes < len(PDF_SIGNATURE):
            raise ValueError("PDF response limit is too small")
        if self.max_redirects < 0 or self.max_selected_pdfs < 1:
            raise ValueError("PDF redirect and selection limits must be non-negative")


@dataclass(frozen=True)
class HuataiPdfParseLimits:
    """Strict worker-only limits for deterministic text-layer extraction."""

    max_pages: int = 50
    max_content_stream_bytes_per_page: int = 8 * 1024 * 1024
    max_content_stream_bytes: int = 64 * 1024 * 1024
    max_extracted_characters_per_page: int = 20_000
    max_extracted_characters: int = 250_000
    parser_deadline_seconds: float = 20.0
    minimum_meaningful_characters: int = 20

    def __post_init__(self) -> None:
        if min(
            self.max_pages,
            self.max_content_stream_bytes_per_page,
            self.max_content_stream_bytes,
            self.max_extracted_characters_per_page,
            self.max_extracted_characters,
            self.minimum_meaningful_characters,
        ) < 1 or self.parser_deadline_seconds <= 0:
            raise ValueError("PDF parsing limits must be positive")


@dataclass(frozen=True)
class HuataiPdfExtractionResult:
    """Safe, immutable output from one bounded official PDF extraction."""

    canonical_pdf_url: str
    byte_count: int
    page_count: int | None
    document_metadata: tuple[tuple[str, str], ...]
    extracted_text: str
    extracted_character_count: int
    extraction_status: str
    failure_category: str | None
    ocr_required: bool
    title: str | None = None
    publication_date: date | None = None
    report_type: str | None = None
    report_author: str | None = None
    document_metadata_author: str | None = None
    parser_diagnostics: tuple[str, ...] = ()
    proxy_tunnel_failure: bool = False


class _Response(Protocol):
    headers: object

    def read(self, size: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def __enter__(self) -> "_Response": ...
    def __exit__(self, *args: object) -> None: ...


class _PdfFailure(Exception):
    def __init__(self, category: str, *, proxy_tunnel_failure: bool = False) -> None:
        self.category = category
        self.proxy_tunnel_failure = proxy_tunnel_failure
        super().__init__(category)


class _OfficialPdfRedirectHandler(HTTPRedirectHandler):
    """Reject untrusted or excessive redirect hops before they are requested."""

    def __init__(self, max_redirects: int) -> None:
        super().__init__()
        self._max_redirects = max_redirects
        self._redirects = 0

    def redirect_request(self, request: Request, *args: object, **kwargs: object) -> Request | None:
        new_url = args[-1] if args else kwargs.get("newurl")
        if not isinstance(new_url, str):
            raise _PdfFailure("off_domain_redirect")
        self._redirects += 1
        if self._redirects > self._max_redirects:
            raise _PdfFailure("redirect_limit_exceeded")
        _validate_pdf_url(new_url, "off_domain_redirect")
        return super().redirect_request(request, *args, **kwargs)


class HuataiPdfTextExtractor:
    """Download one allowlisted PDF and extract its text in a spawned worker."""

    def __init__(
        self,
        download_limits: HuataiPdfDownloadLimits | None = None,
        parse_limits: HuataiPdfParseLimits | None = None,
        opener: Callable[..., _Response] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.download_limits = download_limits or HuataiPdfDownloadLimits()
        self.parse_limits = parse_limits or HuataiPdfParseLimits()
        self._opener = opener
        self._clock = clock

    def extract(self, attachment: HuataiPdfAttachment) -> HuataiPdfExtractionResult:
        """Return a sanitized result without retaining downloaded PDF bytes."""
        try:
            payload, canonical_url = self._download(attachment.url)
        except _PdfFailure as error:
            return _failed_result(
                attachment,
                attachment.url,
                error.category,
                proxy_tunnel_failure=error.proxy_tunnel_failure,
            )

        return self._parse_in_worker(payload, canonical_url, attachment)

    def _download(self, url: str) -> tuple[bytes, str]:
        _validate_pdf_url(url, "invalid_url")
        request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        started = self._clock()
        try:
            with self._open(request) as response:
                canonical_url = response.geturl()
                _validate_pdf_url(canonical_url, "off_domain_redirect")
                if _normalized_content_type(response.headers) != PDF_MEDIA_TYPE:
                    raise _PdfFailure("invalid_content_type")
                content_length = _content_length(response.headers)
                if content_length is not None and content_length > self.download_limits.max_response_bytes:
                    raise _PdfFailure("response_too_large")
                chunks: list[bytes] = []
                total = 0
                while True:
                    if self._clock() - started > self.download_limits.download_deadline_seconds:
                        raise _PdfFailure("download_timeout")
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.download_limits.max_response_bytes:
                        raise _PdfFailure("response_too_large")
                    chunks.append(chunk)
        except _PdfFailure:
            raise
        except TimeoutError:
            raise _PdfFailure("download_timeout") from None
        except OSError as error:
            message = str(error).lower()
            raise _PdfFailure(
                "network_error",
                proxy_tunnel_failure="tunnel" in message and "502" in message,
            ) from None
        except Exception:
            raise _PdfFailure("network_error") from None

        payload = b"".join(chunks)
        if not payload.startswith(PDF_SIGNATURE):
            raise _PdfFailure("invalid_pdf_signature")
        return payload, canonical_url

    def _open(self, request: Request) -> _Response:
        if self._opener is not None:
            return self._opener(request, timeout=self.download_limits.socket_timeout_seconds)
        handler = _OfficialPdfRedirectHandler(self.download_limits.max_redirects)
        return build_opener(handler).open(
            request,
            timeout=self.download_limits.socket_timeout_seconds,
        )

    def _parse_in_worker(
        self,
        payload: bytes,
        canonical_url: str,
        attachment: HuataiPdfAttachment,
    ) -> HuataiPdfExtractionResult:
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=_parse_pdf_worker,
            args=(sender, payload, self.parse_limits),
        )
        outcome: object | None = None
        try:
            process.start()
            sender.close()
            if receiver.poll(self.parse_limits.parser_deadline_seconds):
                outcome = receiver.recv()
                process.join()
            elif process.is_alive():
                process.terminate()
                process.join()
                return _failed_result(attachment, canonical_url, "parser_timeout", len(payload))
            else:
                process.join()
                return _failed_result(attachment, canonical_url, "parser_crashed", len(payload))
        except (EOFError, OSError):
            return _failed_result(attachment, canonical_url, "parser_crashed", len(payload))
        finally:
            receiver.close()
            sender.close()
            if process.is_alive():
                process.terminate()
                process.join()
            process.close()

        if not isinstance(outcome, dict):
            return _failed_result(attachment, canonical_url, "parser_crashed", len(payload))
        category = outcome.get("failure_category")
        if category is not None:
            return _failed_result(
                attachment,
                canonical_url,
                category if isinstance(category, str) else "malformed_pdf",
                len(payload),
                page_count=outcome.get("page_count") if isinstance(outcome.get("page_count"), int) else None,
                metadata=_metadata_from_outcome(outcome.get("metadata")),
                ocr_required=outcome.get("ocr_required") is True,
                parser_diagnostics=_diagnostics_from_outcome(outcome.get("diagnostics")),
            )
        text = outcome.get("text")
        page_count = outcome.get("page_count")
        if not isinstance(text, str) or not isinstance(page_count, int):
            return _failed_result(attachment, canonical_url, "parser_crashed", len(payload))
        metadata = _metadata_from_outcome(outcome.get("metadata"))
        title = attachment.listing_title or _metadata_value(metadata, "Title")
        return HuataiPdfExtractionResult(
            canonical_pdf_url=canonical_url,
            byte_count=len(payload),
            page_count=page_count,
            document_metadata=metadata,
            extracted_text=text,
            extracted_character_count=len(text),
            extraction_status="success",
            failure_category=None,
            ocr_required=False,
            title=title,
            publication_date=attachment.publication_date,
            report_type=attachment.report_type,
            report_author=attachment.report_author,
            document_metadata_author=_metadata_value(metadata, "Author"),
            parser_diagnostics=_diagnostics_from_outcome(outcome.get("diagnostics")),
        )


def _validate_pdf_url(url: str, failure_category: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise _PdfFailure("unsupported_scheme")
    if (
        parsed.hostname not in HTFC_DOMAINS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path.lower().endswith(".pdf")
    ):
        raise _PdfFailure(failure_category)


def _normalized_content_type(headers: object) -> str:
    value = getattr(headers, "get", lambda *_: "")("Content-Type", "")
    return str(value).split(";", 1)[0].strip().lower()


def _content_length(headers: object) -> int | None:
    value = getattr(headers, "get", lambda *_: None)("Content-Length", None)
    try:
        length = int(str(value))
    except (TypeError, ValueError):
        return None
    return length if length >= 0 else None


def _parse_pdf_worker(
    sender: Connection,
    payload: bytes,
    limits: HuataiPdfParseLimits,
) -> None:
    """Parse bounded bytes in a Windows-compatible spawned process."""
    diagnostics_handler = _PypdfDiagnosticHandler()
    logger = logging.getLogger("pypdf")
    previous_handlers = list(logger.handlers)
    previous_level = logger.level
    previous_filters = list(logger.filters)
    previous_propagate = logger.propagate
    previous_disabled = logger.disabled
    try:
        logger.handlers = [diagnostics_handler]
        logger.setLevel(logging.WARNING)
        logger.filters = []
        logger.propagate = False
        logger.disabled = False
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(payload), strict=True, root_object_recovery_limit=0)
        if reader.is_encrypted:
            sender.send({"failure_category": "encrypted_pdf", "diagnostics": diagnostics_handler.categories})
            return
        page_count = len(reader.pages)
        if page_count > limits.max_pages:
            sender.send(
                {
                    "failure_category": "page_limit_exceeded",
                    "page_count": page_count,
                    "diagnostics": diagnostics_handler.categories,
                }
            )
            return
        metadata = _sanitize_metadata(reader.metadata)
        content_stream_total = 0
        pages: list[str] = []
        extracted_total = 0
        image_evidence = False
        for page_number, page in enumerate(reader.pages, start=1):
            stream_size = _content_stream_size(page)
            content_stream_total += stream_size
            if (
                stream_size > limits.max_content_stream_bytes_per_page
                or content_stream_total > limits.max_content_stream_bytes
            ):
                sender.send(
                    {
                        "failure_category": "content_stream_limit_exceeded",
                        "page_count": page_count,
                        "metadata": metadata,
                        "diagnostics": diagnostics_handler.categories,
                    }
                )
                return
            text = page.extract_text() or ""
            if len(text) > limits.max_extracted_characters_per_page:
                sender.send(
                    {
                        "failure_category": "text_limit_exceeded",
                        "page_count": page_count,
                        "metadata": metadata,
                        "diagnostics": diagnostics_handler.categories,
                    }
                )
                return
            extracted_total += len(text)
            if extracted_total > limits.max_extracted_characters:
                sender.send(
                    {
                        "failure_category": "text_limit_exceeded",
                        "page_count": page_count,
                        "metadata": metadata,
                        "diagnostics": diagnostics_handler.categories,
                    }
                )
                return
            pages.append(text)
            image_evidence = image_evidence or _has_image_xobject(page)
        cleaned = _clean_extracted_pages(tuple(pages))
        if _meaningful_character_count(cleaned) < limits.minimum_meaningful_characters:
            sender.send(
                {
                    "failure_category": "ocr_required" if image_evidence else "empty_text",
                    "page_count": page_count,
                    "metadata": metadata,
                    "ocr_required": image_evidence,
                    "diagnostics": diagnostics_handler.categories,
                }
            )
            return
        sender.send(
            {
                "text": cleaned,
                "page_count": page_count,
                "metadata": metadata,
                "diagnostics": diagnostics_handler.categories,
            }
        )
    except Exception:
        sender.send(
            {
                "failure_category": "malformed_pdf",
                "diagnostics": diagnostics_handler.categories,
            }
        )
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        logger.filters = previous_filters
        logger.propagate = previous_propagate
        logger.disabled = previous_disabled
        sender.close()


class _PypdfDiagnosticHandler(logging.Handler):
    """Capture a bounded allowlist of parser diagnostics inside the worker only."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self._categories: list[str] = []

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(self._categories)

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage().lower()
        if "xref table not zero-indexed" in message:
            if "non_zero_indexed_xref" not in self._categories:
                self._categories.append("non_zero_indexed_xref")


def _content_stream_size(page: object) -> int:
    contents = getattr(page, "get_contents")()
    if contents is None:
        return 0
    return len(contents.get_data())


def _has_image_xobject(page: object) -> bool:
    try:
        resources = page.get("/Resources")
        xobjects = resources.get("/XObject") if resources is not None else None
        if xobjects is None:
            return False
        for value in xobjects.values():
            candidate = value.get_object()
            if candidate.get("/Subtype") == "/Image":
                return True
    except Exception:
        return False
    return False


def _sanitize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None or not hasattr(metadata, "items"):
        return ()
    values: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if len(values) >= 16 or isinstance(value, bytes):
            continue
        normalized_key = str(key).lstrip("/").strip()
        normalized_value = str(value).strip()
        if not normalized_key or not normalized_value:
            continue
        values.append((normalized_key[:64], normalized_value[:512]))
    return tuple(values)


def _metadata_from_outcome(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        return ()
    return tuple(
        (key, item)
        for key, item in value
        if isinstance(key, str) and isinstance(item, str)
    )[:16]


def _diagnostics_from_outcome(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        return ()
    allowed = {"non_zero_indexed_xref", "parser_warning"}
    return tuple(item for item in value if isinstance(item, str) and item in allowed)


def _metadata_value(metadata: tuple[tuple[str, str], ...], key: str) -> str | None:
    return next((value for name, value in metadata if name == key), None)


def _clean_extracted_pages(pages: tuple[str, ...]) -> str:
    cleaned_pages: list[str] = []
    for number, page in enumerate(pages, start=1):
        lines = []
        for line in normalize("NFC", page).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            normalized_line = " ".join(line.split())
            if normalized_line and not re.fullmatch(r"(?:第\s*)?\d+(?:\s*页)?", normalized_line):
                lines.append(normalized_line)
        if lines:
            marker = "" if number == 1 else f"--- Page {number} ---\n"
            cleaned_pages.append(marker + "\n".join(lines))
    return "\n\n".join(cleaned_pages).strip()


def _meaningful_character_count(text: str) -> int:
    return sum(character.isalnum() for character in text)


def _failed_result(
    attachment: HuataiPdfAttachment,
    canonical_url: str,
    category: str,
    byte_count: int = 0,
    *,
    page_count: int | None = None,
    metadata: tuple[tuple[str, str], ...] = (),
    ocr_required: bool = False,
    parser_diagnostics: tuple[str, ...] = (),
    proxy_tunnel_failure: bool = False,
) -> HuataiPdfExtractionResult:
    return HuataiPdfExtractionResult(
        canonical_pdf_url=canonical_url,
        byte_count=byte_count,
        page_count=page_count,
        document_metadata=metadata,
        extracted_text="",
        extracted_character_count=0,
        extraction_status="failed",
        failure_category=category,
        ocr_required=ocr_required,
        title=attachment.listing_title or _metadata_value(metadata, "Title"),
        publication_date=attachment.publication_date,
        report_type=attachment.report_type,
        report_author=attachment.report_author,
        document_metadata_author=_metadata_value(metadata, "Author"),
        parser_diagnostics=parser_diagnostics,
        proxy_tunnel_failure=proxy_tunnel_failure,
    )
