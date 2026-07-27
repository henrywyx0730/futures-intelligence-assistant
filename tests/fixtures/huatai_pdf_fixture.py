"""Small deterministic PDF byte fixtures generated without external tools."""

from __future__ import annotations


def chinese_text_layer_pdf(author: str = "Analyst") -> bytes:
    """Return one strict PDF page whose ToUnicode map extracts Chinese text."""
    cmap = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
4 beginbfchar
<4E2D> <4E2D>
<6587> <6587>
<6D4B> <6D4B>
<8BD5> <8BD5>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
    text = b"BT /F1 18 Tf 72 720 Td <4E2D65876D4B8BD5> Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 8 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /Identity-H /Encoding /Identity-H /DescendantFonts [5 0 R] /ToUnicode 6 0 R >>",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Identity-H /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /DW 1000 >>",
        b"<< /Length " + str(len(cmap)).encode() + b" >>\nstream\n" + cmap + b"endstream",
        b"<< /Title (Fallback) /Author (" + author.encode("latin-1") + b") /CreationDate (D:20260721120000) >>",
        b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream",
    ]
    return _assemble_pdf(objects, root="1 0 R", info="7 0 R")


def non_zero_indexed_xref_pdf() -> bytes:
    """Return a text PDF whose xref starts at one, provoking pypdf's known diagnostic."""
    document = basic_text_pdf("market report")
    return document.replace(b"xref\n0 6\n", b"xref\n1 6\n", 1)


def basic_text_pdf(text: str = "market report") -> bytes:
    """Return one strict Latin text-layer PDF for resource-limit tests."""
    encoded = text.encode("latin-1", errors="replace")
    stream = b"BT /F1 12 Tf 72 720 Td (" + encoded + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    return _assemble_pdf(objects, root="1 0 R")


def blank_pdf(page_count: int = 1) -> bytes:
    """Return strict blank pages without a text layer or image evidence."""
    pages = " ".join(f"{index} 0 R" for index in range(3, 3 + page_count)).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + pages + b"] /Count " + str(page_count).encode() + b" >>",
    ]
    objects.extend(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
        for _ in range(page_count)
    )
    return _assemble_pdf(objects, root="1 0 R")


def image_only_pdf() -> bytes:
    """Return one strict page with image evidence but no text layer."""
    image = b"\x00"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 4 0 R >> >> >>",
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n" + image + b"\nendstream",
    ]
    return _assemble_pdf(objects, root="1 0 R")


def _assemble_pdf(objects: list[bytes], *, root: str, info: str | None = None) -> bytes:
    output = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = []
    for index, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root {root}"
    if info is not None:
        trailer += f" /Info {info}"
    output.extend(f"{trailer} >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)
