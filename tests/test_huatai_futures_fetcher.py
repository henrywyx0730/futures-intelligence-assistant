"""Tests for bounded, HTML-only Huatai Futures report fetching."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest

from futures_intelligence.fetchers import (
    HuataiFuturesReportFetcher,
    HuataiReportListingItem,
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
    def test_scopes_listing_items_to_explicit_report_section_containers(self) -> None:
        listing = (FIXTURE_DIRECTORY / "htfc_report_sections.html").read_text(
            encoding="utf-8"
        )

        result = discover_listing_links(
            listing, "https://htfc.com/main/yjzx/ssrdph/index.shtml"
        )

        self.assertEqual(len(result.report_items), 24)
        self.assertEqual(len(result.html_detail_links), 8)
        self.assertEqual(len(result.pdf_attachment_links), 16)
        self.assertEqual(
            result.report_items[0],
            HuataiReportListingItem(
                canonical_url="https://htfc.com/wz_upload/topic-newest.pdf",
                link_kind="pdf_attachment",
                listing_title="专题最新报告",
                publication_date=date(2026, 7, 26),
                report_type="专题报告",
                section_position=0,
                item_position=0,
            ),
        )
        self.assertEqual(result.report_items[8].report_type, "周期报告")
        self.assertEqual(result.report_items[8].link_kind, "html_detail")
        self.assertEqual(result.report_items[16].report_type, "策略报告")
        self.assertEqual(result.report_items[16].publication_date, date(2026, 7, 26))
        self.assertEqual(
            result.report_items[0].listing_title,
            "专题最新报告",
        )
        self.assertNotIn("交割资质", (item.listing_title for item in result.report_items))
        self.assertEqual(len(result.ignored_non_report_links), 5)
        self.assertIn("https://htfc.com/wz_upload/png_upload/20251231/delivery.pdf", result.ignored_non_report_links)
        self.assertIn("https://htfc.com/wz_upload/ranking.pdf", result.ignored_non_report_links)
        self.assertIn("https://example.com/footer.pdf", result.ignored_non_report_links)

    def test_classifies_mixed_listing_links_with_stable_deduplication(self) -> None:
        listing = """
        <div class="ztreport_box"><div class="compre_top"><p><span>专题报告</span></p></div><ul class="clranking">
        <li>2026-07-10 <a href="/main/a/20260710/80180965.shtml">HTML one</a></li>
        <li>2026-07-10 <a href="/wz_upload/20260710/report.pdf">PDF one</a></li>
        <li>2026-07-11 <a href="https://www.htfc.com/main/a/20260711/80180966.shtml">HTML two</a></li>
        <li>2026-07-10 <a href="https://htfc.com/wz_upload/20260710/report.pdf">PDF duplicate</a></li>
        <li>2026-07-10 <a href="/main/a/20260710/80180965.shtml">HTML duplicate</a></li>
        <li><a href="//a/20260712/80180967.shtml">Legacy protocol-relative</a></li>
        <li><a href="https://example.com/report.shtml">Off domain</a></li>
        <li><a href="javascript:void(0)">Malformed legacy</a></li>
        <li><a href="/main/yjzx/other.shtml">Unrelated official path</a></li>
        </ul></div>
        <a href="//a/20260712/80180967.shtml">Legacy protocol-relative</a>
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
        self.assertEqual(result.pdf_attachments[0].title, "PDF one")
        self.assertEqual(
            result.unsupported_links,
            (
                "https://a/20260712/80180967.shtml",
                "https://example.com/report.shtml",
                "javascript:void(0)",
                "https://htfc.com/main/yjzx/other.shtml",
                "https://a/20260712/80180967.shtml",
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
                '<div class="ztreport_box"><div class="compre_top"><p><span>专题报告</span></p></div><ul class="clranking"><li>2026-07-15 '
                '<a href="/wz_upload/20260715/gold.pdf">Gold PDF</a>'
                '</li></ul></div>',
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
                return FakeResponse(
                    url,
                    '<div class="ztreport_box"><div class="compre_top"><p><span>专题报告</span></p></div><ul class="clranking"><li>2026-07-10 '
                    '<a href="/main/a/20260710/80180965.shtml">Empty</a>'
                    '</li></ul></div>',
                )
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
