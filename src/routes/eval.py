# src/routes/eval.py
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config import get_settings

router = APIRouter(tags=["eval"])
templates = Jinja2Templates(directory="templates")


@router.get("/eval/latest")
def eval_latest():
    s = get_settings()
    p = s.storage_root / "eval" / "dashboard" / "latest.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="No evaluation output found yet.")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/eval/download")
def eval_download(kind: str = Query(..., pattern="^(summary|per_query|metrics_csv)$")):
    s = get_settings()
    base = s.storage_root / "eval" / "runs" / "vector"

    mapping = {
        "summary": base / "summary.json",
        "per_query": base / "per_query.jsonl",
        "metrics_csv": base / "metrics.csv",
    }
    p = mapping[kind]
    if not p.exists():
        raise HTTPException(status_code=404, detail="Requested eval file not found.")
    return FileResponse(str(p), filename=p.name)


@router.get("/eval/dashboard", response_class=HTMLResponse)
def eval_dashboard(request: Request):
    s = get_settings()

    # Try rich generated dashboard first (vector vs hybrid comparison)
    rich_path = s.storage_root / "eval" / "dashboard" / "eval_dashboard.html"
    if rich_path.exists():
        return HTMLResponse(content=rich_path.read_text(encoding="utf-8"))

    # Fallback to basic template if rich dashboard not generated yet
    return templates.TemplateResponse("eval_dashboard.html", {"request": request})