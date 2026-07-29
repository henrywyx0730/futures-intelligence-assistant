"""Tests for PDF research-report normalization."""

from datetime import date, datetime, timedelta, timezone
import json
from types import SimpleNamespace
import unittest

from futures_intelligence.collectors.research_report_pdf_adapter import (
    ResearchReportPDFMarketInformationAdapter,
)
from futures_intelligence.fetchers import HuataiPdfExtractionResult


def _successful_result(**overrides: object) -> HuataiPdfExtractionResult:
    """Return a direct, network-free concrete PDF extraction result."""
    values: dict[str, object] = {
        "canonical_pdf_url": "https://htfc.com/wz_upload/20260727/report.pdf",
        "byte_count": 0,
        "page_count": 0,
        "document_metadata": (("Title", "Document title"), ("Author", "FreeUser")),
        "extracted_text": "  Extracted report text without semantic rewriting.  ",
        "extracted_character_count": 0,
        "extraction_status": "success",
        "failure_category": None,
        "ocr_required": False,
        "title": "Huatai Futures Black Commodities Special Report",
        "publication_date": date(2026, 7, 27),
        "report_type": "专题报告",
        "report_author": "Research Analyst",
        "document_metadata_author": "FreeUser",
        "parser_diagnostics": ("non_zero_indexed_xref",),
    }
    values.update(overrides)
    return HuataiPdfExtractionResult(**values)  # type: ignore[arg-type]


def _mutable_result(
    document_metadata: object,
    parser_diagnostics: object,
) -> SimpleNamespace:
    """Return a protocol-shaped mutable external extraction fixture."""
    return SimpleNamespace(
        canonical_pdf_url="https://example.test/report.pdf",
        byte_count=0,
        page_count=0,
        document_metadata=document_metadata,
        extracted_text="Extracted text",
        extracted_character_count=0,
        extraction_status="success",
        ocr_required=False,
        title="Report title",
        publication_date=date(2026, 7, 27),
        report_type=None,
        report_author=None,
        document_metadata_author=None,
        parser_diagnostics=parser_diagnostics,
    )


SOURCE_METADATA = {
    "source": "Huatai Futures",
    "provider": "huatai_futures",
    "category": ["macro", "energy"],
    "regions": ["China"],
    "reliability_score": 5,
}


class ResearchReportPDFMarketInformationAdapterTests(unittest.TestCase):
    """Verify safe conversion of PDF extraction records."""

    def setUp(self) -> None:
        self.adapter = ResearchReportPDFMarketInformationAdapter()

    def test_converts_concrete_huatai_result_with_date_only_timestamp(self) -> None:
        item = self.adapter.to_market_information(_successful_result(), SOURCE_METADATA)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.title, "Huatai Futures Black Commodities Special Report")
        self.assertEqual(item.source, "Huatai Futures")
        self.assertEqual(item.source_type, "research_report")
        self.assertEqual(item.content, "Extracted report text without semantic rewriting.")
        self.assertEqual(item.url, "https://htfc.com/wz_upload/20260727/report.pdf")
        self.assertEqual(item.category, ("macro", "energy"))
        self.assertEqual(item.regions, ("China",))
        self.assertEqual(item.reliability_score, 5)
        self.assertEqual(item.commodities, ())
        self.assertEqual(item.published_time.tzinfo.key, "Asia/Shanghai")
        self.assertEqual(item.published_time.utcoffset(), timedelta(hours=8))
        self.assertEqual(item.published_time, datetime(2026, 7, 27, tzinfo=item.published_time.tzinfo))
        self.assertEqual(item.metadata["publication_date"], "2026-07-27")
        self.assertEqual(item.metadata["published_time_precision"], "date")
        json.dumps(item.to_dict())

    def test_rejects_naive_and_timezone_aware_datetime_publication_values(self) -> None:
        for publication_value in (
            datetime(2026, 7, 27, 9, 30),
            datetime(2026, 7, 27, 9, 30, tzinfo=timezone.utc),
        ):
            with self.subTest(publication_value=publication_value):
                self.assertIsNone(
                    self.adapter.to_market_information(
                        _successful_result(publication_date=publication_value),
                        SOURCE_METADATA,
                    )
                )

    def test_preserves_separate_complete_provenance_including_zero_values(self) -> None:
        item = self.adapter.to_market_information(_successful_result(), SOURCE_METADATA)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.metadata["provider"], "huatai_futures")
        self.assertEqual(item.metadata["report_type"], "专题报告")
        self.assertEqual(item.metadata["report_author"], "Research Analyst")
        self.assertEqual(item.metadata["document_metadata_author"], "FreeUser")
        self.assertEqual(
            item.metadata["document_metadata"],
            {"Title": "Document title", "Author": "FreeUser"},
        )
        self.assertEqual(item.metadata["parser_diagnostics"], ["non_zero_indexed_xref"])
        self.assertEqual(item.metadata["page_count"], 0)
        self.assertEqual(item.metadata["byte_count"], 0)
        self.assertEqual(item.metadata["extracted_character_count"], 0)

    def test_detaches_external_and_source_metadata(self) -> None:
        document_metadata = {"Keywords": ["oil"]}
        parser_diagnostics = ["non_zero_indexed_xref"]
        source_metadata = {
            **SOURCE_METADATA,
            "category": list(SOURCE_METADATA["category"]),
            "regions": list(SOURCE_METADATA["regions"]),
        }
        result = _mutable_result(document_metadata, parser_diagnostics)

        item = self.adapter.to_market_information(result, source_metadata)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(source_metadata["category"], ["macro", "energy"])
        document_metadata["Keywords"].append("gold")
        parser_diagnostics.append("other")
        source_metadata["category"].append("metals")
        self.assertEqual(item.metadata["document_metadata"], {"Keywords": ["oil"]})
        self.assertEqual(item.metadata["parser_diagnostics"], ["non_zero_indexed_xref"])
        self.assertEqual(item.category, ("macro", "energy"))
        self.assertEqual(source_metadata["category"], ["macro", "energy", "metals"])

    def test_rejects_unsupported_external_metadata(self) -> None:
        invalid_results = (
            _successful_result(document_metadata=(("Author", b"bytes"),)),
            _successful_result(document_metadata=(("Keywords", {"oil"}),)),
            _successful_result(document_metadata=((1, "not a string key"),)),
            _successful_result(parser_diagnostics=(object(),)),
        )

        for result in invalid_results:
            with self.subTest(result=result):
                self.assertIsNone(self.adapter.to_market_information(result, SOURCE_METADATA))

    def test_returns_none_for_unusable_extractions(self) -> None:
        for description, overrides in (
            ("failed extraction", {"extraction_status": "failed"}),
            ("OCR-required extraction", {"ocr_required": True}),
            ("empty title", {"title": ""}),
            ("whitespace title", {"title": "  "}),
            ("missing date", {"publication_date": None}),
            ("missing URL", {"canonical_pdf_url": None}),
            ("whitespace URL", {"canonical_pdf_url": "  "}),
            ("missing content", {"extracted_text": None}),
            ("empty content", {"extracted_text": ""}),
            ("whitespace content", {"extracted_text": "  "}),
        ):
            with self.subTest(description=description):
                self.assertIsNone(
                    self.adapter.to_market_information(
                        _successful_result(**overrides), SOURCE_METADATA
                    )
                )

    def test_ignores_source_scope_commodities(self) -> None:
        item = self.adapter.to_market_information(
            _successful_result(),
            {**SOURCE_METADATA, "commodities": ("crude_oil",)},
        )

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.commodities, ())


if __name__ == "__main__":
    unittest.main()
