from __future__ import annotations

import json

from src.config import get_settings
from src.pipeline.job_store import JobStore
from src.pipeline.stages import Stage
from src.ingestion.hashing import sha256_bytes
from src.ingestion.registry import load_manifest, save_manifest, upsert_doc
from src.utils.atomic_io import atomic_write_json, atomic_write_jsonl

from src.processing.extract_pdf import extract_pdf_pages
from src.processing.extract_docx import extract_docx_pages
from src.processing.clean import clean_page_text
from src.processing.chunk import chunk_processed_doc


def _guess_file_type(file_name: str) -> str:
    name = file_name.lower()
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".docx"):
        return "docx"
    return "unknown"


class PipelineRunner:
    """
    Implemented stages:
      - INGEST
      - EXTRACT
      - CLEAN
      - CHUNK
    Remaining stages stay pending.
    """

    def __init__(self, store: JobStore):
        self.store = store

    # ---------- helpers ----------
    def _manifest_doc_file_size(self, manifest: dict, doc_id: str):
        for x in manifest.get("docs", []):
            if x.get("doc_id") == doc_id:
                return x.get("file_size")
        return None

    def _manifest_doc_raw_path(self, manifest: dict, doc_id: str):
        for x in manifest.get("docs", []):
            if x.get("doc_id") == doc_id:
                return x.get("raw_path")
        return None

    # ---------- Stage 2: INGEST ----------
    def _ingest(self, job_id: str) -> None:
        s = get_settings()
        job = self.store.read_job(job_id)

        raw_dir = s.raw_dir / job.collection_id
        manifest = load_manifest(s.collections_dir, job.collection_id)

        for d in job.docs:
            d.status = "running"
            self.store.write_job(job)

            raw_path = raw_dir / d.file_name
            if not raw_path.exists():
                d.status = "failed"
                d.fail_reason = "RAW_NOT_FOUND"
                self.store.write_job(job)
                continue

            data = raw_path.read_bytes()
            doc_id = sha256_bytes(data)
            d.doc_id = doc_id

            file_type = _guess_file_type(d.file_name)
            upsert_doc(
                manifest,
                doc_id=doc_id,
                sha256=doc_id,
                file_name=d.file_name,
                file_type=file_type,
                file_size=len(data),
                raw_path=str(raw_path),
                status="ingested",
            )
            save_manifest(s.collections_dir, job.collection_id, manifest)

            d.status = "done"
            d.fail_reason = None
            self.store.write_job(job)

    # ---------- Stage 3: EXTRACT ----------
    def _extract(self, job_id: str) -> None:
        s = get_settings()
        job = self.store.read_job(job_id)
        raw_dir = s.raw_dir / job.collection_id
        manifest = load_manifest(s.collections_dir, job.collection_id)

        for d in job.docs:
            # only extract docs that successfully ingested
            if d.status != "done" or not d.doc_id or d.fail_reason:
                continue

            d.status = "running"
            self.store.write_job(job)

            raw_path = raw_dir / d.file_name
            if not raw_path.exists():
                d.status = "failed"
                d.fail_reason = "RAW_NOT_FOUND"
                self.store.write_job(job)
                continue

            data = raw_path.read_bytes()
            ftype = _guess_file_type(d.file_name)

            try:
                if ftype == "pdf":
                    pages, full_text_original = extract_pdf_pages(data)
                elif ftype == "docx":
                    pages, full_text_original = extract_docx_pages(data)
                else:
                    raise ValueError("UNSUPPORTED_FILE_TYPE")

                processed = {
                    "collection_id": job.collection_id,
                    "doc_id": d.doc_id,
                    "file_name": d.file_name,
                    "file_type": ftype,
                    "pages": pages,
                    "full_text_original": full_text_original,
                    "full_text_clean": "",
                }

                out_path = s.processed_dir / job.collection_id / f"{d.doc_id}.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(out_path, processed)

                d.counts.pages = len(pages)

                upsert_doc(
                    manifest,
                    doc_id=d.doc_id,
                    sha256=d.doc_id,
                    file_name=d.file_name,
                    file_type=ftype,
                    file_size=len(data),
                    raw_path=str(raw_path),
                    status="extracted",
                )
                save_manifest(s.collections_dir, job.collection_id, manifest)

                d.status = "done"
                d.fail_reason = None
                self.store.write_job(job)

            except Exception as e:
                d.status = "failed"
                d.fail_reason = f"EXTRACT_FAILED: {e}"
                self.store.write_job(job)

    # ---------- Stage 4: CLEAN ----------
    def _clean(self, job_id: str) -> None:
        s = get_settings()
        job = self.store.read_job(job_id)
        manifest = load_manifest(s.collections_dir, job.collection_id)

        for d in job.docs:
            if not d.doc_id or d.fail_reason:
                continue

            d.status = "running"
            self.store.write_job(job)

            in_path = s.processed_dir / job.collection_id / f"{d.doc_id}.json"
            if not in_path.exists():
                d.status = "failed"
                d.fail_reason = "PROCESSED_NOT_FOUND"
                self.store.write_job(job)
                continue

            try:
                obj = json.loads(in_path.read_text(encoding="utf-8"))

                pages = obj.get("pages", [])
                clean_parts = []

                for p in pages:
                    original = (p.get("text_original") or "")
                    text_clean, flags = clean_page_text(original)

                    p["text_clean"] = text_clean

                    base_flags = p.get("flags") or {}
                    base_flags.update(flags)
                    p["flags"] = base_flags

                    if text_clean:
                        clean_parts.append(text_clean)

                obj["pages"] = pages
                obj["full_text_clean"] = "\n\n".join(clean_parts).strip()

                atomic_write_json(in_path, obj)

                # Preserve file_size/raw_path from manifest (safe)
                upsert_doc(
                    manifest,
                    doc_id=d.doc_id,
                    sha256=d.doc_id,
                    file_name=obj.get("file_name", d.file_name),
                    file_type=obj.get("file_type", _guess_file_type(d.file_name)),
                    file_size=self._manifest_doc_file_size(manifest, d.doc_id),
                    raw_path=self._manifest_doc_raw_path(manifest, d.doc_id),
                    status="cleaned",
                )
                save_manifest(s.collections_dir, job.collection_id, manifest)

                d.status = "done"
                d.fail_reason = None
                self.store.write_job(job)

            except Exception as e:
                d.status = "failed"
                d.fail_reason = f"CLEAN_FAILED: {e}"
                self.store.write_job(job)

    # ---------- Stage 5: CHUNK ----------
    def _chunk(self, job_id: str) -> None:
        s = get_settings()
        job = self.store.read_job(job_id)
        manifest = load_manifest(s.collections_dir, job.collection_id)

        for d in job.docs:
            if not d.doc_id or d.fail_reason:
                continue

            d.status = "running"
            self.store.write_job(job)

            in_path = s.processed_dir / job.collection_id / f"{d.doc_id}.json"
            if not in_path.exists():
                d.status = "failed"
                d.fail_reason = "PROCESSED_NOT_FOUND"
                self.store.write_job(job)
                continue

            try:
                processed = json.loads(in_path.read_text(encoding="utf-8"))
                chunks = chunk_processed_doc(processed)

                out_path = s.chunks_dir / job.collection_id / f"{d.doc_id}.jsonl"
                atomic_write_jsonl(out_path, chunks)

                d.counts.chunks = len(chunks)

                if len(chunks) == 0:
                    d.status = "failed"
                    d.fail_reason = "NO_VALID_CHUNKS"
                    self.store.write_job(job)
                    continue

                upsert_doc(
                    manifest,
                    doc_id=d.doc_id,
                    sha256=d.doc_id,
                    file_name=processed.get("file_name", d.file_name),
                    file_type=processed.get("file_type", _guess_file_type(d.file_name)),
                    file_size=self._manifest_doc_file_size(manifest, d.doc_id),
                    raw_path=self._manifest_doc_raw_path(manifest, d.doc_id),
                    status="chunked",
                )
                save_manifest(s.collections_dir, job.collection_id, manifest)

                d.status = "done"
                d.fail_reason = None
                self.store.write_job(job)

            except Exception as e:
                d.status = "failed"
                d.fail_reason = f"CHUNK_FAILED: {e}"
                self.store.write_job(job)

    # ---------- run ----------
    def run(self, job_id: str) -> None:
        job = self.store.read_job(job_id)
        try:
            self.store.stage_running(job, Stage.INGEST.value)
            self._ingest(job_id)
            job = self.store.read_job(job_id)
            self.store.stage_done(job, Stage.INGEST.value)

            self.store.stage_running(job, Stage.EXTRACT.value)
            self._extract(job_id)
            job = self.store.read_job(job_id)
            self.store.stage_done(job, Stage.EXTRACT.value)

            self.store.stage_running(job, Stage.CLEAN.value)
            self._clean(job_id)
            job = self.store.read_job(job_id)
            self.store.stage_done(job, Stage.CLEAN.value)

            self.store.stage_running(job, Stage.CHUNK.value)
            self._chunk(job_id)
            job = self.store.read_job(job_id)
            self.store.stage_done(job, Stage.CHUNK.value)

            any_success = any(d.doc_id and d.status == "done" and not d.fail_reason for d in job.docs)
            if not any_success:
                self.store.fail_job(job, Stage.CHUNK.value, "ALL_DOCS_FAILED_BY_CHUNK")
                return

            job.status = "done"
            job.current_stage = Stage.CHUNK.value
            self.store.write_job(job)

        except Exception as e:
            job = self.store.read_job(job_id)
            self.store.fail_job(job, job.current_stage, f"RUNNER_EXCEPTION: {e}")
