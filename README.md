# DocuChat

> > This is my Capstone Project: "Reducing Hallucination in Retrieval-Augmented Generation Using Hybrid Vector–Graph Integration with Evidence Grounding"

This repository implements a deterministic, restart-safe document processing pipeline designed to prepare unstructured documents for Retrieval-Augmented Generation (RAG), semantic search, and downstream AI applications.

The system transforms raw documents into structured, citation-accurate semantic chunks while preserving full traceability to the original source.

Stages 0 through 5 establish a stable foundation for scalable embedding, indexing, and retrieval.

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
Ready for Embedding (Stage 6)
```

Each stage produces deterministic outputs, enabling restart safety, append-only processing, and reproducibility.

---

# Stage 0 - Storage and Job Foundation

Stage 0 establishes the storage structure and job tracking system.

Key responsibilities:

* Create deterministic collection and job identifiers
* Track document processing state across stages
* Maintain append-safe manifest files
* Ensure atomic file writes to prevent corruption
* Enable safe restart and resume behavior

This stage provides the backbone for all subsequent processing.

---

# Stage 1 - File Registration

Documents are registered into the system and associated with a collection.

Key outcomes:

* Document identity is established
* Collection manifest is updated
* Job record is created
* Document becomes eligible for processing

This stage ensures every document is tracked consistently.

---

# Stage 2 - Ingestion

Raw files are ingested into the pipeline and assigned a stable identity.

Key outcomes:

* Each document receives a deterministic `doc_id`
* Files are stored in the raw storage directory
* Collection manifest is updated
* Job state reflects ingestion completion

This stage establishes the permanent identity of each document.

---

# Stage 3 - Extraction

Document contents are extracted into structured text form while preserving reading order.

Supported formats:

* PDF
* DOCX

Key outcomes:

* Page-level text extraction
* Full document text assembly
* Preservation of page boundaries
* Storage of extracted content in structured JSON format

This stage converts binary files into structured textual representations.

---

# Stage 4 - Cleaning

Extracted text is normalized and prepared for downstream semantic processing.

Key outcomes:

* Removal of extraction artifacts
* Text normalization
* Garbage detection and filtering
* Clean text stored alongside original text

Both original and cleaned text are preserved to maintain citation accuracy.

This ensures embedding quality while preserving source fidelity.

---

# Stage 5 - Semantic Chunking

Documents are divided into meaningful semantic units suitable for embedding and retrieval.

This stage uses a semantic-first strategy that respects document structure.

Key outcomes:

* Paragraph-based chunking
* Structure-aware segmentation
* Deterministic chunk identifiers
* Citation-accurate span tracking
* Stable chunk boundaries

Each chunk includes:

* Document reference
* Page number
* Exact source span offsets
* Original text (for citations)
* Clean text (for embeddings)

Chunking preserves meaning while enabling efficient retrieval.

---

# Stage 6 - Embedding

Stage 6 converts semantic chunks into vector representations for similarity search and downstream retrieval.

This stage introduces a cache-aware embedding mechanism to prevent redundant computation.

Key outcomes:

* Each chunk’s cleaned text is transformed into a vector representation
* A versioned embedder identity ensures reproducibility
* Embeddings are stored per document in structured JSONL format
* Cross-document content reuse prevents duplicate embedding calls
* Per-document idempotency ensures safe reruns
* Embedding metrics are recorded for observability

This stage guarantees that identical content is embedded only once while preserving document-level traceability.

After completion, all chunks are vectorized and ready for indexing.

---

# Stage 7 - Indexing

Stage 7 builds a fast semantic search index over all embedded vectors in a collection.

This stage prepares the system for efficient retrieval.

Key outcomes:

* All document vectors are validated for consistency
* Deterministic ordering ensures reproducible index builds
* A FAISS-based ANN index is created
* Metadata mapping preserves chunk-to-document traceability
* Index artifacts are written atomically for safety

The result is a millisecond-level semantic search capability across the entire collection.

--- 

# Failure Handling

The pipeline follows a document-level failure model.

If a document fails:

* The failure is recorded
* Other documents continue processing
* The job only fails if all documents fail

This ensures robustness in mixed document collections.

---

# Restart Safety

The pipeline is fully restart-safe.

If execution stops unexpectedly, restarting the job will:

* Resume from the last incomplete stage
* Skip already processed documents
* Avoid duplicate outputs
* Maintain consistency

No manual recovery steps are required.

---

# Current Pipeline Status

Stages completed:

* Stage 0 - Storage and Job Foundation
* Stage 1 - File Registration
* Stage 2 - Ingestion
* Stage 3 - Extraction
* Stage 4 - Cleaning
* Stage 5 - Semantic Chunking
* Stage 6 - Embedding
* Stage 7 - Indexing

Yed to do:

* Stage 8 - Graph
* Stage 9 - Retrieval + grounded generation
* Stage 10 - Chat persistence

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

 - **Foundation for Scalable Retrieval Systems**
The pipeline is designed to integrate seamlessly with embedding models, vector indexes (FAISS), and graph-based retrieval, forming the backbone of a scalable RAG system.

---

