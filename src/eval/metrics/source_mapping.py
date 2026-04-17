# src/eval/metrics/source_mapping.py
from __future__ import annotations

SOURCE_ID_TO_FILENAME: dict[str, str] = {
    "source_1": "Vetrivel_Maheswaran_Capstone_Project_Checkpoint_2.pdf",
    "source_2": "Maheswaran_Vetrivel_project_proposal.docx",
    "source_3": "Iot_project_proposal.docx",
}

def gold_source_ids_to_filenames(source_ids: list[str]) -> set[str]:
    out = set()
    for sid in (source_ids or []):
        fname = SOURCE_ID_TO_FILENAME.get(str(sid))
        if fname:
            out.add(fname)
    return out