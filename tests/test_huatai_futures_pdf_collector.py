"""Tests for bounded Huatai Futures PDF research-report collection."""

from datetime import date
import unittest

from futures_intelligence.collectors.huatai_futures_pdf import (
    HuataiFuturesPdfResearchReportCollector,
)
from futures_intelligence.collectors.research_report_pdf_adapter import (
    ResearchReportPDFMarketInformationAdapter,
)
from futures_intelligence.fetchers import (
    HuataiListingDiscovery,
    HuataiPdfExtractionResult,
    HuataiReportListingItem,
)
from futures_intelligence.fetchers.huatai_futures import HuataiListingStructureError


def _listing_item(
    url: str,
    *,
    publication_date: date | None = date(2026, 7, 26),
    section_position: int = 0,
    item_position: int = 0,
) -> HuataiReportListingItem:
    """Build one valid PDF listing item without network access."""
    return HuataiReportListingItem(
        canonical_url=url,
        link_kind="pdf_attachment",
        listing_title=f"Report {item_position}",
        publication_date=publication_date,
        report_type="专题报告",
        section_position=section_position,
        item_position=item_position,
    )


def _extraction_result(
    item: HuataiReportListingItem,
    **overrides: object,
) -> HuataiPdfExtractionResult:
    """Build a successful, provenance-rich extractor result for one item."""
    values: dict[str, object] = {
        "canonical_pdf_url": item.canonical_url,
        "byte_count": 2048,
        "page_count": 2,
        "document_metadata": (("Author", "FreeUser"),),
        "extracted_text": f"Extracted text for {item.listing_title}.",
        "extracted_character_count": 36,
        "extraction_status": "success",
        "failure_category": None,
        "ocr_required": False,
        "title": item.listing_title,
        "publication_date": item.publication_date,
        "report_type": item.report_type,
        "report_author": "Research Analyst",
        "document_metadata_author": "FreeUser",
        "parser_diagnostics": ("non_zero_indexed_xref",),
    }
    values.update(overrides)
    return HuataiPdfExtractionResult(**values)  # type: ignore[arg-type]


class _ListingFetcher:
    """Record listing-only calls without performing requests."""

    def __init__(self, discovery: HuataiListingDiscovery) -> None:
        self.discovery = discovery
        self.calls = 0

    def discover_listing(self) -> HuataiListingDiscovery:
        self.calls += 1
        return self.discovery


class _PdfExtractor:
    """Return configured results while recording bounded extraction attempts."""

    def __init__(self, results: dict[str, HuataiPdfExtractionResult]) -> None:
        self.results = results
        self.urls: list[str] = []

    def extract(self, attachment: object) -> HuataiPdfExtractionResult:
        url = attachment.url  # type: ignore[attr-defined]
        self.urls.append(url)
        return self.results[url]


class _RecordingAdapter:
    """Record collector adapter calls without normalizing an item."""

    def __init__(self) -> None:
        self.calls = 0

    def to_market_information(
        self,
        result: HuataiPdfExtractionResult,
        source_metadata: object,
    ) -> None:
        del result, source_metadata
        self.calls += 1
        return None


class HuataiFuturesPdfResearchReportCollectorTests(unittest.TestCase):
    """Verify deterministic, non-analytical PDF collection behavior."""

    def _collector(
        self,
        items: tuple[HuataiReportListingItem, ...],
        results: dict[str, HuataiPdfExtractionResult],
        *,
        max_selected_pdfs: object = 3,
    ) -> tuple[HuataiFuturesPdfResearchReportCollector, _ListingFetcher, _PdfExtractor]:
        listing_fetcher = _ListingFetcher(
            HuataiListingDiscovery(
                report_items=items,
                recognized_report_section_count=1,
                recognized_report_list_count=1,
            )
        )
        extractor = _PdfExtractor(results)
        return (
            HuataiFuturesPdfResearchReportCollector(
                listing_fetcher=listing_fetcher,
                pdf_extractor=extractor,
                adapter=ResearchReportPDFMarketInformationAdapter(),
                source="Huatai Futures",
                category=("macro", "energy"),
                regions=("China",),
                reliability_score=5,
                provider="huatai_futures",
                max_selected_pdfs=max_selected_pdfs,
            ),
            listing_fetcher,
            extractor,
        )

    def test_collects_newest_selected_reports_in_deterministic_order(self) -> None:
        older = _listing_item("https://htfc.com/wz_upload/older.pdf", publication_date=date(2026, 7, 24))
        newest_second = _listing_item(
            "https://htfc.com/wz_upload/newest-second.pdf",
            publication_date=date(2026, 7, 26),
            section_position=1,
        )
        newest_first = _listing_item(
            "https://htfc.com/wz_upload/newest-first.pdf",
            publication_date=date(2026, 7, 26),
            section_position=0,
        )
        collector, listing_fetcher, extractor = self._collector(
            (older, newest_second, newest_first),
            {
                older.canonical_url: _extraction_result(older),
                newest_second.canonical_url: _extraction_result(newest_second),
                newest_first.canonical_url: _extraction_result(newest_first),
            },
            max_selected_pdfs=2,
        )

        information = collector.collect()

        self.assertEqual(listing_fetcher.calls, 1)
        self.assertEqual(
            extractor.urls,
            [newest_first.canonical_url, newest_second.canonical_url],
        )
        self.assertEqual(
            [item.url for item in information],
            [newest_first.canonical_url, newest_second.canonical_url],
        )
        self.assertEqual(information[0].commodities, ())
        self.assertEqual(information[0].metadata["report_author"], "Research Analyst")
        self.assertEqual(information[0].metadata["document_metadata_author"], "FreeUser")
        self.assertEqual(information[0].metadata["published_time_precision"], "date")

    def test_deduplicates_urls_before_selection_and_keeps_first_listing_record(self) -> None:
        first = _listing_item("https://htfc.com/wz_upload/duplicate.pdf", item_position=0)
        duplicate = _listing_item(
            "https://htfc.com/wz_upload/duplicate.pdf",
            publication_date=date(2026, 7, 27),
            item_position=1,
        )
        collector, _, extractor = self._collector(
            (first, duplicate),
            {first.canonical_url: _extraction_result(first)},
        )

        information = collector.collect()

        self.assertEqual(extractor.urls, [first.canonical_url])
        self.assertEqual([item.title for item in information], [first.listing_title])

    def test_places_undated_records_after_dated_records(self) -> None:
        undated = _listing_item("https://htfc.com/wz_upload/undated.pdf", publication_date=None)
        dated = _listing_item("https://htfc.com/wz_upload/dated.pdf", publication_date=date(2026, 7, 26))
        collector, _, extractor = self._collector(
            (undated, dated),
            {
                undated.canonical_url: _extraction_result(undated),
                dated.canonical_url: _extraction_result(dated),
            },
            max_selected_pdfs=2,
        )

        collector.collect()

        self.assertEqual(extractor.urls, [dated.canonical_url, undated.canonical_url])

    def test_uses_item_position_after_section_position_for_same_date_ties(self) -> None:
        later_item = _listing_item(
            "https://htfc.com/wz_upload/later-item.pdf",
            item_position=1,
        )
        earlier_item = _listing_item(
            "https://htfc.com/wz_upload/earlier-item.pdf",
            item_position=0,
        )
        collector, _, extractor = self._collector(
            (later_item, earlier_item),
            {
                later_item.canonical_url: _extraction_result(later_item),
                earlier_item.canonical_url: _extraction_result(earlier_item),
            },
            max_selected_pdfs=2,
        )

        collector.collect()

        self.assertEqual(
            extractor.urls,
            [earlier_item.canonical_url, later_item.canonical_url],
        )

    def test_preserves_original_discovery_order_when_all_sort_fields_match(self) -> None:
        discovered_first = _listing_item("https://htfc.com/wz_upload/z-first.pdf")
        discovered_second = _listing_item("https://htfc.com/wz_upload/a-second.pdf")
        collector, _, extractor = self._collector(
            (discovered_first, discovered_second),
            {
                discovered_first.canonical_url: _extraction_result(discovered_first),
                discovered_second.canonical_url: _extraction_result(discovered_second),
            },
            max_selected_pdfs=2,
        )

        information = collector.collect()

        self.assertEqual(
            extractor.urls,
            [discovered_first.canonical_url, discovered_second.canonical_url],
        )
        self.assertEqual(
            [item.url for item in information],
            [discovered_first.canonical_url, discovered_second.canonical_url],
        )

        limited_collector, _, limited_extractor = self._collector(
            (discovered_first, discovered_second),
            {
                discovered_first.canonical_url: _extraction_result(discovered_first),
                discovered_second.canonical_url: _extraction_result(discovered_second),
            },
            max_selected_pdfs=1,
        )

        limited_collector.collect()

        self.assertEqual(limited_extractor.urls, [discovered_first.canonical_url])

    def test_skips_controlled_extraction_failures_and_adapter_rejections(self) -> None:
        malformed = _listing_item("https://htfc.com/wz_upload/malformed.pdf", item_position=0)
        rejected = _listing_item("https://htfc.com/wz_upload/rejected.pdf", item_position=1)
        ocr_required = _listing_item(
            "https://htfc.com/wz_upload/ocr-required.pdf",
            item_position=2,
        )
        empty_text = _listing_item(
            "https://htfc.com/wz_upload/empty-text.pdf",
            item_position=3,
        )
        successful = _listing_item("https://htfc.com/wz_upload/successful.pdf", item_position=4)
        collector, _, extractor = self._collector(
            (malformed, rejected, ocr_required, empty_text, successful),
            {
                malformed.canonical_url: _extraction_result(
                    malformed,
                    extraction_status="failed",
                    failure_category="malformed_pdf",
                    extracted_text="",
                ),
                rejected.canonical_url: _extraction_result(rejected, extracted_text="  "),
                ocr_required.canonical_url: _extraction_result(
                    ocr_required,
                    extraction_status="failed",
                    failure_category="ocr_required",
                    ocr_required=True,
                    extracted_text="",
                ),
                empty_text.canonical_url: _extraction_result(
                    empty_text,
                    extraction_status="failed",
                    failure_category="empty_text",
                    extracted_text="",
                ),
                successful.canonical_url: _extraction_result(successful),
            },
            max_selected_pdfs=5,
        )

        information = collector.collect()

        self.assertEqual(
            extractor.urls,
            [
                malformed.canonical_url,
                rejected.canonical_url,
                ocr_required.canonical_url,
                empty_text.canonical_url,
                successful.canonical_url,
            ],
        )
        self.assertEqual([item.url for item in information], [successful.canonical_url])

    def test_logs_unique_candidate_count_before_applying_selection_limit(self) -> None:
        items = tuple(
            _listing_item(
                f"https://htfc.com/wz_upload/report-{position}.pdf",
                item_position=position,
            )
            for position in range(3)
        )
        collector, _, _ = self._collector(
            items,
            {item.canonical_url: _extraction_result(item) for item in items},
            max_selected_pdfs=1,
        )

        with self.assertLogs(
            "futures_intelligence.collectors.huatai_futures_pdf", level="INFO"
        ) as logs:
            collector.collect()

        self.assertTrue(
            any("retained 3 unique candidates, and selected 1" in entry for entry in logs.output)
        )

    def test_propagates_listing_request_failures(self) -> None:
        class FailingListingFetcher:
            def discover_listing(self) -> HuataiListingDiscovery:
                raise OSError("network unavailable")

        collector = HuataiFuturesPdfResearchReportCollector(
            listing_fetcher=FailingListingFetcher(),
            pdf_extractor=_PdfExtractor({}),
            adapter=ResearchReportPDFMarketInformationAdapter(),
            source="Huatai Futures",
            category=(),
            regions=(),
            reliability_score=5,
            provider="huatai_futures",
            max_selected_pdfs=1,
        )

        with self.assertRaisesRegex(OSError, "network unavailable"):
            collector.collect()

    def test_propagates_listing_structure_failures(self) -> None:
        class StructurallyInvalidListingFetcher:
            def discover_listing(self) -> HuataiListingDiscovery:
                raise HuataiListingStructureError(
                    "Huatai Futures report listing structure was not recognized"
                )

        collector = HuataiFuturesPdfResearchReportCollector(
            listing_fetcher=StructurallyInvalidListingFetcher(),
            pdf_extractor=_PdfExtractor({}),
            adapter=ResearchReportPDFMarketInformationAdapter(),
            source="Huatai Futures",
            category=(),
            regions=(),
            reliability_score=5,
            provider="huatai_futures",
            max_selected_pdfs=1,
        )

        with self.assertRaises(HuataiListingStructureError):
            collector.collect()

    def test_returns_empty_when_recognized_listing_has_no_pdf_attachments(self) -> None:
        listing_fetcher = _ListingFetcher(
            HuataiListingDiscovery(
                recognized_report_section_count=1,
                recognized_report_list_count=1,
            )
        )
        extractor = _PdfExtractor({})
        adapter = _RecordingAdapter()
        collector = HuataiFuturesPdfResearchReportCollector(
            listing_fetcher=listing_fetcher,
            pdf_extractor=extractor,
            adapter=adapter,  # type: ignore[arg-type]
            source="Huatai Futures",
            category=(),
            regions=(),
            reliability_score=5,
            provider="huatai_futures",
            max_selected_pdfs=1,
        )

        self.assertEqual(collector.collect(), [])
        self.assertEqual(listing_fetcher.calls, 1)
        self.assertEqual(extractor.urls, [])
        self.assertEqual(adapter.calls, 0)

    def test_rejects_invalid_selection_limits(self) -> None:
        item = _listing_item("https://htfc.com/wz_upload/report.pdf")
        results = {item.canonical_url: _extraction_result(item)}
        for value in (None, False, 0, -1, 1.5, "1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "max_selected_pdfs"):
                    self._collector((item,), results, max_selected_pdfs=value)

    def test_rejects_invalid_source_metadata_before_listing_discovery(self) -> None:
        invalid_values = (
            ("source", "", "source"),
            ("source", "  ", "source"),
            ("source", 1, "source"),
            ("provider", "", "provider"),
            ("provider", "  ", "provider"),
            ("provider", 1, "provider"),
            ("category", "macro", "category"),
            ("category", ("",), "category"),
            ("category", (1,), "category"),
            ("category", ["macro"], "category"),
            ("regions", "China", "regions"),
            ("regions", ("",), "regions"),
            ("regions", (1,), "regions"),
            ("regions", ["China"], "regions"),
            ("reliability_score", 0, "reliability_score"),
            ("reliability_score", 6, "reliability_score"),
            ("reliability_score", -1, "reliability_score"),
            ("reliability_score", False, "reliability_score"),
            ("reliability_score", 3.0, "reliability_score"),
            ("reliability_score", "3", "reliability_score"),
            ("reliability_score", None, "reliability_score"),
        )
        for field, value, error_field in invalid_values:
            with self.subTest(field=field, value=value):
                listing_fetcher = _ListingFetcher(
                    HuataiListingDiscovery(
                        recognized_report_section_count=1,
                        recognized_report_list_count=1,
                    )
                )
                kwargs: dict[str, object] = {
                    "source": "Huatai Futures",
                    "provider": "huatai_futures",
                    "category": ("macro",),
                    "regions": ("China",),
                    "reliability_score": 5,
                }
                kwargs[field] = value
                with self.assertRaisesRegex(ValueError, error_field):
                    HuataiFuturesPdfResearchReportCollector(
                        listing_fetcher=listing_fetcher,
                        pdf_extractor=_PdfExtractor({}),
                        adapter=ResearchReportPDFMarketInformationAdapter(),
                        max_selected_pdfs=1,
                        **kwargs,  # type: ignore[arg-type]
                    )
                self.assertEqual(listing_fetcher.calls, 0)


if __name__ == "__main__":
    unittest.main()
