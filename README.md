# DocuChat

> Capstone Project (Phase 1 – Vector-Only Baseline)

This repository implements the Vector-Only baseline system for my Capstone Project:

"Reducing Hallucination in Retrieval-Augmented Generation Using Hybrid Vector–Graph Integration with Evidence Grounding"

This version establishes the controlled experimental baseline using:

- Deterministic document pipeline
- Cache-aware embedding
- FAISS vector indexing
- Vector-based retrieval
- Evidence-grounded answer generation
- Evaluation-ready logging

The Hybrid Vector–Graph system will be introduced in Phase 2 and compared against this baseline.

---

# Overview

The pipeline converts raw documents into structured semantic units through the following progression:

```
Raw Files
   ↓
Ingestion
   ↓
Extraction
   ↓
Cleaning
   ↓
Chunking
   ↓
Embedding (Vectorization)
   ↓
FAISS Indexing
   ↓
Vector Retrieval
   ↓
Grounded Generation
   ↓
Evaluation Logging
```

Each stage produces deterministic outputs, enabling restart safety, append-only processing, and reproducibility.

---

# Current System Status (Vector Baseline Complete)

Implemented:

* Stage 0 – Storage & Job Foundation
* Stage 1 – File Registration
* Stage 2 – Ingestion
* Stage 3 – Extraction
* Stage 4 – Cleaning
* Stage 5 – Semantic Chunking
* Stage 6 – Cache-Aware Embedding
* Stage 7 – FAISS Indexing
* Stage 8 – Vector Retrieval
* Stage 9 – Evidence-Grounded Generation
* Stage 10 – Evaluation Logging

Planned (Phase 2 – Hybrid System):

* Graph Construction
* Hybrid Vector–Graph Retrieval
* Graph Contribution Analysis
* Hybrid vs Vector Metric Comparison

---

# Vector-Only Baseline Capabilities

This baseline system implements a production-grade Vector RAG architecture with:

- Dense embedding generation (BGE-M3 / configurable model)
- Content-based embedding reuse (cross-document deduplication)
- Deterministic FAISS index construction
- Vector similarity retrieval (L2 metric)
- Strict evidence-grounded prompt design
- Mandatory citation enforcement
- Evaluation-ready structured query logging

The system supports:

- Recall@K evaluation
- Citation precision analysis
- Unsupported claim detection
- Abstention accuracy measurement
- Retrieval vs generation error separation

---

# Evaluation Framework (Baseline)

All queries are logged in structured JSONL format, enabling offline metric computation.

Each log entry records:

- Retrieved chunks before rerank
- Final context chunks
- Generated answer
- Extracted citations
- Retrieval configuration
- Embedder identity

Metrics computed offline:

- Recall@K
- Citation Precision
- Unsupported Claim Rate
- Abstention Accuracy
- Answer Correctness (optional rubric)

This establishes the experimental control condition for later Hybrid comparison.

---

## Bells and Whistles

This project goes far beyond a basic document parser and demonstrates production-grade Retrieval-Augmented Generation (RAG) pipeline engineering, with strong emphasis on reliability, traceability, and scalability.

Some standout features:

 - **Deterministic Pipeline Architecture**
Every collection, document, and chunk uses stable cryptographic IDs. This guarantees reproducibility, enables safe reprocessing, and prevents duplication or corruption across runs.

 - **Citation-Accurate Chunking**
Chunks are not arbitrary text slices. Each chunk maps precisely to its original document span (`page_num`, `start_char`, `end_char`), ensuring trustworthy citations and verifiable retrieval.

 - **Dual-Text Storage for Accuracy and Performance**
The system preserves both the original extracted text (for faithful display and citations) and a cleaned version (optimized for embeddings and retrieval quality).

 - **Structure-Aware Semantic Chunking**
Chunking respects document structure such as headings and paragraph boundaries, producing retrieval units aligned with meaning rather than arbitrary length limits.

 - **Failure-Resilient Processing Model**
The pipeline isolates failures at the document level. One problematic file does not break the entire job, ensuring robustness in real-world heterogeneous document collections.

 - **Transparent and Inspectable Storage Layout**
All intermediate outputs (processed text, chunks, job state, manifest) are stored in human-readable formats. This enables debugging, auditing, and full pipeline visibility.

 - **Append-Safe and Restart-Safe Design**
New documents can be added without reprocessing existing data. The system safely resumes from interruptions without recomputing completed stages.

 - **Production-Grade Job Tracking and Monitoring**
Each job tracks stage-level and document-level progress, enabling real-time monitoring and precise failure diagnostics.

 - **Clear Separation of Pipeline Stages**
Each stage (INGEST → EXTRACT → CLEAN → CHUNK) is independently modular, making the system maintainable, testable, and extensible.

 - **Foundation for Hybrid Retrieval Research**
The system is intentionally architected to support future integration of graph-based retrieval. The current implementation serves as the controlled Vector baseline for experimental comparison.

---

