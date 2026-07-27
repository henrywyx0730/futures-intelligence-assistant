"""Tests for bounded, text-layer-only Huatai PDF extraction."""

from datetime import date
from types import SimpleNamespace
import unittest

from pypdf import PdfWriter

from futures_intelligence.fetchers.huatai_pdf import (
    HuataiPdfAttachment,
    HuataiPdfDownloadLimits,
    HuataiPdfParseLimits,
    HuataiPdfTextExtractor,
)
from tests.fixtures.huatai_pdf_fixture import (
    basic_text_pdf,
    blank_pdf,
    chinese_text_layer_pdf,
    image_only_pdf,
    non_zero_indexed_xref_pdf,
)


class FakePdfResponse:
    """A bounded mocked HTTP response used without network access."""

    def __init__(
        self,
        url: str,
        body: bytes,
        content_type: str = "application/pdf",
        content_length: str | None = None,
    ) -> None:
        self._url = url
        self._body = body
        self._position = 0
        values = {"Content-Type": content_type}
        if content_length is not None:
            values["Content-Length"] = content_length
        self.headers = SimpleNamespace(
            get=lambda key, default=None: values.get(key, default),
        )

    def __enter__(self) -> "FakePdfResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._position
        chunk = self._body[self._position : self._position + size]
        self._position += len(chunk)
        return chunk


class HuataiPdfTextExtractorTests(unittest.TestCase):
    def test_keeps_document_metadata_author_separate_from_report_author(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf",
            listing_title="原油专题报告",
            publication_date=date(2026, 7, 21),
            report_type="专题报告",
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, chinese_text_layer_pdf(author="FreeUser"))

        result = HuataiPdfTextExtractor(
            opener=opener,
            parse_limits=HuataiPdfParseLimits(minimum_meaningful_characters=1),
        ).extract(attachment)

        self.assertEqual(result.extraction_status, "success")
        self.assertIsNone(result.report_author)
        self.assertEqual(result.document_metadata_author, "FreeUser")
        self.assertEqual(dict(result.document_metadata)["Author"], "FreeUser")

    def test_returns_known_xref_diagnostic_without_failing_extraction(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf"
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, non_zero_indexed_xref_pdf())

        result = HuataiPdfTextExtractor(
            opener=opener,
            parse_limits=HuataiPdfParseLimits(minimum_meaningful_characters=1),
        ).extract(attachment)

        self.assertEqual(result.extraction_status, "success")
        self.assertEqual(result.parser_diagnostics, ("non_zero_indexed_xref",))
    def test_extracts_chinese_text_with_listing_title_precedence(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf",
            listing_title="华泰期货显式标题",
            publication_date=date(2026, 7, 21),
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, chinese_text_layer_pdf())

        result = HuataiPdfTextExtractor(
            opener=opener,
            parse_limits=HuataiPdfParseLimits(minimum_meaningful_characters=1),
        ).extract(attachment)

        self.assertEqual(result.extraction_status, "success")
        self.assertEqual(result.extracted_text, "中文测试")
        self.assertEqual(result.title, "华泰期货显式标题")
        self.assertEqual(result.publication_date, date(2026, 7, 21))
        self.assertIsNone(result.report_author)
        self.assertEqual(result.document_metadata_author, "Analyst")
        self.assertNotIn("CreationDate", dict(result.document_metadata).get("Title", ""))

    def test_classifies_empty_text_without_image_evidence_separately_from_ocr(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/blank.pdf"
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, blank_pdf())

        result = HuataiPdfTextExtractor(opener=opener).extract(attachment)

        self.assertEqual(result.failure_category, "empty_text")
        self.assertFalse(result.ocr_required)

    def test_classifies_image_only_pdf_as_ocr_required_without_running_ocr(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/image-only.pdf"
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, image_only_pdf())

        result = HuataiPdfTextExtractor(opener=opener).extract(attachment)

        self.assertEqual(result.failure_category, "ocr_required")
        self.assertTrue(result.ocr_required)

    def test_rejects_encrypted_pdf_without_attempting_decryption(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/encrypted.pdf"
        )
        encrypted = _encrypted_pdf()

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, encrypted)

        result = HuataiPdfTextExtractor(opener=opener).extract(attachment)

        self.assertEqual(result.failure_category, "encrypted_pdf")

    def test_enforces_page_and_text_limits_inside_the_worker(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf"
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, basic_text_pdf("A" * 120))

        page_result = HuataiPdfTextExtractor(
            opener=opener,
            parse_limits=HuataiPdfParseLimits(max_pages=1, minimum_meaningful_characters=1),
        ).extract(attachment)
        text_result = HuataiPdfTextExtractor(
            opener=opener,
            parse_limits=HuataiPdfParseLimits(
                max_extracted_characters_per_page=100,
                max_extracted_characters=100,
                minimum_meaningful_characters=1,
            ),
        ).extract(attachment)

        self.assertEqual(page_result.extraction_status, "success")
        self.assertEqual(text_result.failure_category, "text_limit_exceeded")

    def test_enforces_content_stream_limit_inside_the_worker(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf"
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, basic_text_pdf("market report"))

        result = HuataiPdfTextExtractor(
            opener=opener,
            parse_limits=HuataiPdfParseLimits(
                max_content_stream_bytes_per_page=1,
                max_content_stream_bytes=1,
            ),
        ).extract(attachment)

        self.assertEqual(result.failure_category, "content_stream_limit_exceeded")

    def test_rejects_non_pdf_content_type_before_parsing(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf",
            listing_title="Explicit listing title",
            publication_date=date(2026, 7, 21),
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(
                attachment.url,
                b"%PDF-1.7\n",
                content_type="text/html; charset=utf-8",
            )

        result = HuataiPdfTextExtractor(opener=opener).extract(attachment)

        self.assertEqual(result.extraction_status, "failed")
        self.assertEqual(result.failure_category, "invalid_content_type")
        self.assertEqual(result.byte_count, 0)

    def test_rejects_invalid_signature_after_pdf_content_type(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf"
        )

        def opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, b"not a PDF")

        result = HuataiPdfTextExtractor(opener=opener).extract(attachment)

        self.assertEqual(result.failure_category, "invalid_pdf_signature")

    def test_enforces_content_length_and_streamed_response_limits(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf"
        )
        limits = HuataiPdfDownloadLimits(max_response_bytes=8)

        def length_opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, b"%PDF-1.7", content_length="9")

        def streamed_opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, b"%PDF-1.7-more")

        self.assertEqual(
            HuataiPdfTextExtractor(opener=length_opener, download_limits=limits)
            .extract(attachment)
            .failure_category,
            "response_too_large",
        )
        self.assertEqual(
            HuataiPdfTextExtractor(opener=streamed_opener, download_limits=limits)
            .extract(attachment)
            .failure_category,
            "response_too_large",
        )

    def test_enforces_download_deadline_and_rejects_off_domain_redirects(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf"
        )
        times = iter((0.0, 31.0))

        def slow_opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse(attachment.url, b"%PDF-1.7")

        def redirected_opener(request: object, timeout: float) -> FakePdfResponse:
            del request, timeout
            return FakePdfResponse("https://example.com/report.pdf", b"%PDF-1.7")

        self.assertEqual(
            HuataiPdfTextExtractor(opener=slow_opener, clock=lambda: next(times))
            .extract(attachment)
            .failure_category,
            "download_timeout",
        )
        self.assertEqual(
            HuataiPdfTextExtractor(opener=redirected_opener)
            .extract(attachment)
            .failure_category,
            "off_domain_redirect",
        )

    def test_preserves_explicit_listing_metadata_without_pdf_date_inference(self) -> None:
        attachment = HuataiPdfAttachment(
            url="https://htfc.com/wz_upload/20260721/report.pdf",
            listing_title="华泰期货专题报告",
            publication_date=date(2026, 7, 21),
        )

        self.assertEqual(attachment.listing_title, "华泰期货专题报告")
        self.assertEqual(attachment.publication_date, date(2026, 7, 21))

    def test_limit_models_are_immutable_and_use_safe_defaults(self) -> None:
        download = HuataiPdfDownloadLimits()
        parse = HuataiPdfParseLimits()

        self.assertEqual(download.socket_timeout_seconds, 10.0)
        self.assertEqual(download.download_deadline_seconds, 30.0)
        self.assertEqual(download.max_response_bytes, 20 * 1024 * 1024)
        self.assertEqual(download.max_redirects, 3)
        self.assertEqual(parse.max_pages, 50)
        self.assertEqual(parse.max_content_stream_bytes_per_page, 8 * 1024 * 1024)
        self.assertEqual(parse.max_content_stream_bytes, 64 * 1024 * 1024)
        self.assertEqual(parse.parser_deadline_seconds, 20.0)
        with self.assertRaises(Exception):
            download.max_redirects = 4  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()


def _encrypted_pdf() -> bytes:
    from io import BytesIO

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("not-used")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
