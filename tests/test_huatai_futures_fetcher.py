"""Tests for bounded, HTML-only Huatai Futures report fetching."""

from pathlib import Path
from types import SimpleNamespace
import unittest

from futures_intelligence.fetchers import (
    HuataiFuturesReportFetcher,
    discover_listing_links,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, url: str, body: str) -> None:
        self._url = url
        self._body = body.encode("utf-8")
        self.headers = SimpleNamespace(get_content_charset=lambda: "utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]


class HuataiFuturesReportFetcherTests(unittest.TestCase):
    def test_classifies_mixed_listing_links_with_stable_deduplication(self) -> None:
        listing = """
        <a href="/main/a/20260710/80180965.shtml">HTML one</a>
        <a href="/wz_upload/20260710/report.pdf">PDF one</a>
        <a href="https://www.htfc.com/main/a/20260711/80180966.shtml">HTML two</a>
        <a href="https://htfc.com/wz_upload/20260710/report.pdf">PDF duplicate</a>
        <a href="/main/a/20260710/80180965.shtml">HTML duplicate</a>
        <a href="//a/20260712/80180967.shtml">Legacy protocol-relative</a>
        <a href="https://example.com/report.shtml">Off domain</a>
        <a href="javascript:void(0)">Malformed legacy</a>
        <a href="/main/yjzx/other.shtml">Unrelated official path</a>
        """

        result = discover_listing_links(
            listing, "https://htfc.com/main/yjzx/ssrdph/index.shtml"
        )

        self.assertEqual(
            result.html_detail_links,
            (
                "https://htfc.com/main/a/20260710/80180965.shtml",
                "https://www.htfc.com/main/a/20260711/80180966.shtml",
            ),
        )
        self.assertEqual(
            result.pdf_attachment_links,
            ("https://htfc.com/wz_upload/20260710/report.pdf",),
        )
        self.assertEqual(
            result.unsupported_links,
            (
                "https://a/20260712/80180967.shtml",
                "https://example.com/report.shtml",
                "javascript:void(0)",
                "https://htfc.com/main/yjzx/other.shtml",
            ),
        )

    def test_discovers_official_links_in_order_and_parses_metadata(self) -> None:
        listing = (FIXTURE_DIRECTORY / "htfc_listing.html").read_text(encoding="utf-8")
        detail = (FIXTURE_DIRECTORY / "htfc_detail.html").read_text(encoding="utf-8")
        calls: list[str] = []

        def opener(request: object, timeout: float) -> FakeResponse:
            del timeout
            url = request.full_url  # type: ignore[attr-defined]
            calls.append(url)
            return FakeResponse(url, listing if url.endswith("index.shtml") else detail)

        result = HuataiFuturesReportFetcher(
            "https://htfc.com/main/yjzx/ssrdph/index.shtml",
            max_reports=2,
            opener=opener,
        ).fetch_reports()

        self.assertEqual(result.discovered_link_count, 2)
        self.assertEqual(len(result.reports), 2)
        self.assertEqual(result.selected_urls[0], "https://htfc.com/main/a/20260710/80180965.shtml")
        report = result.reports[0]
        self.assertEqual(report.title, "Crude Oil Weekly Outlook")
        self.assertEqual(report.published_time.utcoffset().total_seconds(), 28800)
        self.assertEqual(report.report_type, "策略报告")
        self.assertEqual(report.author, "张三")
        self.assertNotIn("Navigation", report.content)
        self.assertNotIn("Footer", report.content)
        self.assertEqual(len(calls), 3)

    def test_rejects_off_domain_redirect_and_response_size(self) -> None:
        def redirecting_opener(request: object, timeout: float) -> FakeResponse:
            del request, timeout
            return FakeResponse("https://example.com/redirect", "<html></html>")

        with self.assertRaisesRegex(ValueError, "official htfc.com"):
            HuataiFuturesReportFetcher(
                "https://htfc.com/main/yjzx/ssrdph/index.shtml",
                opener=redirecting_opener,
            ).fetch_reports()

    def test_pdf_only_listing_is_classified_without_fetching_attachments(self) -> None:
        calls: list[str] = []

        def opener(request: object, timeout: float) -> FakeResponse:
            del timeout
            url = request.full_url  # type: ignore[attr-defined]
            calls.append(url)
            return FakeResponse(
                url,
                '<a href="/wz_upload/20260715/gold.pdf">Gold PDF</a>',
            )

        result = HuataiFuturesReportFetcher(
            "https://htfc.com/main/yjzx/ssrdph/index.shtml",
            opener=opener,
        ).fetch_reports()

        self.assertEqual(result.discovery.html_detail_links, ())  # type: ignore[union-attr]
        self.assertEqual(
            result.discovery.pdf_attachment_links,  # type: ignore[union-attr]
            ("https://htfc.com/wz_upload/20260715/gold.pdf",),
        )
        self.assertEqual(calls, ["https://htfc.com/main/yjzx/ssrdph/index.shtml"])

    def test_returns_no_reports_for_empty_or_malformed_detail_html(self) -> None:
        empty = (FIXTURE_DIRECTORY / "htfc_empty.html").read_text(encoding="utf-8")

        def opener(request: object, timeout: float) -> FakeResponse:
            del timeout
            url = request.full_url  # type: ignore[attr-defined]
            if url.endswith("index.shtml"):
                return FakeResponse(url, '<a href="/main/a/20260710/80180965.shtml">Empty</a>')
            return FakeResponse(url, empty)

        result = HuataiFuturesReportFetcher(
            "https://htfc.com/main/yjzx/ssrdph/index.shtml",
            opener=opener,
        ).fetch_reports()

        self.assertEqual(result.discovered_link_count, 1)
        self.assertEqual(result.reports, ())

        def oversized_opener(request: object, timeout: float) -> FakeResponse:
            del timeout
            return FakeResponse(request.full_url, "x" * 100)  # type: ignore[attr-defined]

        with self.assertRaisesRegex(ValueError, "size limit"):
            HuataiFuturesReportFetcher(
                "https://htfc.com/main/yjzx/ssrdph/index.shtml",
                max_response_bytes=10,
                opener=oversized_opener,
            ).fetch_reports()


if __name__ == "__main__":
    unittest.main()
