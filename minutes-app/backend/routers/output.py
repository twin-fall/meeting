"""
output.py - 실명 복원 + Word 문서 출력 라우터

엔드포인트:
  POST /output/restore      - 가명 → 실명 역치환
  POST /output/export-docx  - Word(.docx) 회의록 생성 & 다운로드
  DELETE /session/clear     - 세션 매핑 메모리 초기화
"""

import io
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from routers import pseudonymize as pm

router         = APIRouter()   # prefix /output
session_router = APIRouter()   # prefix /session


# ── Pydantic 모델 ──────────────────────────────────────────

class RestoreRequest(BaseModel):
    anonymized_text: str
    mapping_table: dict[str, str]          # alias → original


class AttendeeRow(BaseModel):
    name: str = ""
    dept: str = ""
    position: str = ""


class ExportRequest(BaseModel):
    restored_text: str
    mapping_table: dict[str, str]          # alias → original
    meeting_date: str = ""                 # "YYYY-MM-DD HH:MM"
    meeting_type: str = "회의"
    location: str = ""
    attendees: list[AttendeeRow] = []
    agenda: str = ""


# ── /output/restore ────────────────────────────────────────

@router.post("/restore")
async def restore(req: RestoreRequest):
    """가명처리된 텍스트에서 실명을 복원합니다."""
    text = req.anonymized_text
    count = 0

    # 긴 alias 먼저 치환 (중첩 방지)
    for alias, original in sorted(req.mapping_table.items(), key=lambda x: len(x[0]), reverse=True):
        if alias in text:
            occurrences = text.count(alias)
            text = text.replace(alias, original)
            count += occurrences

    return {"restored_text": text, "replaced_count": count}


# ── /output/export-docx ────────────────────────────────────

def _set_vertical_text(cell):
    """python-docx 셀에 세로쓰기(아래→위) 설정."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    td = OxmlElement("w:textDirection")
    td.set(qn("w:val"), "btLr")
    tcPr.append(td)


def _set_cell_font(cell, font_name: str = "맑은 고딕", size_pt: int = 10, bold: bool = False):
    """셀 내 모든 run에 폰트·크기 적용."""
    from docx.oxml.ns import qn
    from docx.shared import Pt

    for para in cell.paragraphs:
        for run in para.runs:
            run.font.name = font_name
            run.font.size = Pt(size_pt)
            run.font.bold = bold
            rPr = run._r.get_or_add_rPr()
            rFonts = rPr.find(qn("w:rFonts"))
            if rFonts is None:
                from docx.oxml import OxmlElement
                rFonts = OxmlElement("w:rFonts")
                rPr.insert(0, rFonts)
            rFonts.set(qn("w:eastAsia"), font_name)


def _add_run(para, text: str, font_name: str = "맑은 고딕", size_pt: int = 10, bold: bool = False):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.shared import Pt

    run = para.add_run(text)
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), font_name)
    return run


def _build_docx(req: ExportRequest) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL

    doc = Document()

    # ── 기본 여백 ──
    section = doc.sections[0]
    section.top_margin    = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin   = Cm(3)
    section.right_margin  = Cm(2)

    # ── 제목 단락 ──────────────────────────────────────────
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = _add_run(title_para, "회  의  록", size_pt=18, bold=True)
    title_run.font.color.rgb = RGBColor(0xC5, 0x1F, 0x2A)

    doc.add_paragraph()   # 빈 줄

    # ── 헤더 표 (2행 6열) ─────────────────────────────────
    # 열 너비: [세로 레이블 ~1.2cm] + [내용 cols ×5]
    hdr_table = doc.add_table(rows=2, cols=6)
    hdr_table.style = "Table Grid"
    hdr_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 열 너비 설정
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    col_widths_cm = [1.2, 3.5, 3.5, 3.5, 3.5, 3.5]
    for i, w in enumerate(col_widths_cm):
        for cell in hdr_table.columns[i].cells:
            cell.width = Cm(w)

    # 행0: 일시 / 장소 / 종류
    labels_row0 = ["일시", req.meeting_date, "장소", req.location, "종류", req.meeting_type]
    for col_idx, text in enumerate(labels_row0):
        cell = hdr_table.cell(0, col_idx)
        cell.text = ""
        para = cell.paragraphs[0]
        is_label = col_idx % 2 == 0
        _add_run(para, text, size_pt=9, bold=is_label)
        _set_cell_font(cell, size_pt=9, bold=is_label)

    # 행1: 참석자 (col0) + 이름 목록 (col1..5 병합)
    cell_label = hdr_table.cell(1, 0)
    cell_label.text = ""
    para_l = cell_label.paragraphs[0]
    _add_run(para_l, "참석자", size_pt=9, bold=True)
    _set_vertical_text(cell_label)

    # col1 ~ col5 병합
    cell_start = hdr_table.cell(1, 1)
    cell_end   = hdr_table.cell(1, 5)
    cell_merged = cell_start.merge(cell_end)
    cell_merged.text = ""
    attendee_names = "  ".join(
        f"{a.name} {a.position}".strip() for a in req.attendees if a.name
    )
    para_a = cell_merged.paragraphs[0]
    _add_run(para_a, attendee_names, size_pt=9)

    doc.add_paragraph()   # 빈 줄

    # ── 안건 단락 ─────────────────────────────────────────
    if req.agenda:
        agenda_para = doc.add_paragraph()
        _add_run(agenda_para, f"안건: {req.agenda}", size_pt=10)
        doc.add_paragraph()

    # ── 내용 표 (N행 × 2열) ───────────────────────────────
    # 행 구분: 빈 줄 기준 단락 분리
    paragraphs = [p.strip() for p in req.restored_text.split("\n") if p.strip()]

    if paragraphs:
        content_table = doc.add_table(rows=len(paragraphs), cols=2)
        content_table.style = "Table Grid"
        content_table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # 열 너비: col0(세로 순번 ~1.2cm), col1(내용)
        for row_idx, para_text in enumerate(paragraphs):
            cell_num  = content_table.cell(row_idx, 0)
            cell_body = content_table.cell(row_idx, 1)

            # 순번 셀 (세로쓰기)
            cell_num.text = ""
            num_para = cell_num.paragraphs[0]
            _add_run(num_para, str(row_idx + 1), size_pt=9)
            _set_vertical_text(cell_num)
            cell_num.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

            # 본문 셀
            cell_body.text = ""
            body_para = cell_body.paragraphs[0]
            _add_run(body_para, para_text, size_pt=10)

        # col0 너비 고정
        for row_idx in range(len(paragraphs)):
            content_table.cell(row_idx, 0).width = Cm(1.2)

    doc.add_paragraph()   # 빈 줄

    # ── 마지막 단락 ───────────────────────────────────────
    end_para = doc.add_paragraph()
    end_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(end_para, "- 끝 -", size_pt=10, bold=True)

    # ── bytes 변환 ────────────────────────────────────────
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


@router.post("/export-docx")
async def export_docx(req: ExportRequest):
    """Word(.docx) 회의록을 생성하고 다운로드 응답을 반환합니다."""
    docx_bytes = _build_docx(req)

    # 파일명: 회의록_YYYYMMDD_종류.docx
    date_part = ""
    if req.meeting_date:
        try:
            dt = datetime.strptime(req.meeting_date[:10], "%Y-%m-%d")
            date_part = dt.strftime("%Y%m%d")
        except ValueError:
            date_part = req.meeting_date[:8].replace("-", "")

    raw_name = f"회의록_{date_part}_{req.meeting_type}.docx"
    encoded  = quote(raw_name, safe="")
    content_disposition = (
        f"attachment; filename=\"minutes.docx\"; filename*=UTF-8''{encoded}"
    )

    # 세션 매핑 즉시 소거
    pm._session_mapping.clear()

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": content_disposition},
    )


# ── /session/clear ─────────────────────────────────────────

@session_router.delete("/clear")
async def clear_session():
    """세션 가명처리 매핑을 메모리에서 소거합니다."""
    pm._session_mapping.clear()
    return {"cleared": True}
