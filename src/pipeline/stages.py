from enum import Enum


class Stage(str, Enum):
    INGEST = "INGEST"
    EXTRACT = "EXTRACT"
    CLEAN = "CLEAN"
    CHUNK = "CHUNK"
    EMBED = "EMBED"
    INDEX = "INDEX"
    GRAPH = "GRAPH"
    DONE = "DONE"


STAGE_ORDER = [
    Stage.INGEST.value,
    Stage.EXTRACT.value,
    Stage.CLEAN.value,
    Stage.CHUNK.value,
    Stage.EMBED.value,
    Stage.INDEX.value,
    Stage.GRAPH.value,
    Stage.DONE.value,
]
