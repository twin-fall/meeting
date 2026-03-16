"""
employee.py - 사원명부 관리 라우터

엔드포인트:
  POST /api/employee/upload  - xlsx/csv 파싱 후 컬럼·행 반환
  POST /api/employee/save    - 컬럼 매핑 적용 후 in-memory 저장
  GET  /api/employee/list    - 저장된 사원 목록 반환
"""

import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()

# ── 세션 메모리 (프로세스 재시작 시 초기화) ──────────────
_raw_rows: list[dict] = []          # 마지막 업로드 원본 행
_employee_db: list[dict] = []       # {name, dept, position} 정규화된 목록


# ── 업로드 ───────────────────────────────────────────────

@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    """xlsx/csv 파일을 파싱해 컬럼명과 행 데이터를 반환합니다."""
    global _raw_rows
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("xlsx", "xls", "csv"):
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다. (.xlsx, .csv만 가능)",
        )

    content = await file.read()
    try:
        import pandas as pd

        df = (
            pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
            if ext == "csv"
            else pd.read_excel(io.BytesIO(content))
        )
        df = df.fillna("")
        _raw_rows = df.to_dict(orient="records")
        return {
            "columns": df.columns.tolist(),
            "rows": _raw_rows,
            "total": len(_raw_rows),
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"파일 파싱 중 오류: {exc}")


# ── 저장 ─────────────────────────────────────────────────

class SaveRequest(BaseModel):
    mapping: dict  # {dept: col_name, name: col_name, position: col_name}


@router.post("/save")
async def save(body: SaveRequest):
    """컬럼 매핑을 적용해 정규화된 사원 목록을 메모리에 저장합니다."""
    global _employee_db
    m = body.mapping

    def _str(row: dict, col: str) -> str:
        return str(row.get(col, "") or "").strip()

    _employee_db = [
        {
            "name":     _str(r, m.get("name", "")),
            "dept":     _str(r, m.get("dept", "")),
            "position": _str(r, m.get("position", "")),
        }
        for r in _raw_rows
        if _str(r, m.get("name", ""))  # 성명이 있는 행만
    ]

    return {"saved": len(_employee_db)}


# ── 조회 ─────────────────────────────────────────────────

@router.get("/list")
async def list_employees():
    """저장된 사원 목록을 반환합니다."""
    return {"employees": _employee_db, "total": len(_employee_db)}
