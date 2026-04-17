# DocuChat

> Capstone Project  
> **Reducing Hallucination in Retrieval-Augmented Generation Using Hybrid Vector–Graph Integration with Evidence Grounding**

A production-grade Retrieval-Augmented Generation system that combines dense vector search with knowledge graph retrieval to deliver evidence-grounded, citation-backed answers from document collections — with measurable hallucination control.

---

## Capstone Details

| Field | Detail |
|---|---|
| **Course** | ISTE 793 — CapstoneITA |
| **Instructor** | Ezgi Siir Kibris, Lecturer, School of Information, |
| **Author** | Vetrivel Maheswaran, Master's in ITA |
| **Institution** | Rochester Institute of Technology |
| **Term** | Spring 2026 |

---

## Problem

RAG systems built on vector-only retrieval fail silently for entity-specific, multi-hop, and cross-document queries — returning semantically similar but factually incomplete chunks. This causes hallucinated answers that appear fluent but are unsupported by source evidence.

---

## Solution

DocuChat combines two complementary retrieval signals:
- **Vector retrieval** — captures semantic similarity using FAISS + BAAI/bge-m3
- **Graph retrieval** — captures entity relationships and structural connections using Neo4j

Answers are generated strictly from retrieved evidence. Every statement requires a citation. If evidence is insufficient, the system returns `"Not found in documents."` rather than hallucinating.

---

## Strategy

1. Documents are ingested, extracted, cleaned, and chunked with structure-aware boundaries
2. Chunks are embedded and indexed into FAISS for vector search
3. A knowledge graph is built from chunks using LLM-extracted entities and relations
4. At query time, both channels retrieve candidates, scores are normalized and fused, a cross-encoder reranker selects the final context
5. The LLM generates a grounded answer with source citations

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.11 |
| Vector Index | FAISS |
| Embeddings | BAAI/bge-m3 (SentenceTransformers) |
| Graph Database | Neo4j |
| Graph Extraction | neo4j-graphrag + GPT-4o-mini |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| LLM | GPT-4o-mini (OpenAI) |
| Embedding Cache | SQLite |
| PDF Extraction | pdfplumber + tesseract OCR |
| Package Manager | uv |

---

## Pipeline

### Baseline — Vector Only
```
Upload → Ingest → Extract → Clean → Chunk → Embed → FAISS Index
                                                          ↓
Query → Embed Query → FAISS Search → Rerank → Prompt → LLM → Answer + Citations
```

### Hybrid — Vector + Graph
```
Upload → Ingest → Extract → Clean → Chunk → Embed → FAISS Index
                                               ↓
                                         Neo4j Graph (entities + relations)
                                                          ↓
Query → Embed Query → FAISS Search ──┐
                    → Graph Search ──┴→ Merge + Normalize → Rerank → Prompt → LLM → Answer + Citations
```

**Hybrid scoring:**
```
S_hybrid = 0.75 × S_vector + 0.25 × S_graph
```

---

## Setup & Run

### 1. Clone the repository
```bash
git clone https://github.com/Vetrivel07/DocuChat.git
cd docuchat
```

### 2. Create virtual environment
```bash
uv venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
uv sync
```

### 4. Configure environment
```bash
cp .env
```

Edit `.env` and set:
```
OPENAI_API_KEY=your_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
LLM_MODEL=model_name
RERANK_MODEL=model_name
GRAPH_LLM_MODEL=model_name
GRAPH_EMBEDDING_MODEL=model_name
```

### 5. Run the project
```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

Open `http://127.0.0.1:8080` in your browser.

> **Note:** Neo4j must be running locally or via AuraDB for hybrid mode. Vector-only mode works without Neo4j.

---

## Evaluation

A structured gold dataset of **102 queries** across 3 documents was used to evaluate both retrieval modes under identical conditions.

### Query Distribution

| Type | Count |
|---|---|
| Single-chunk factual | 40 |
| Multi-chunk | 18 |
| Abstention (unanswerable) | 19 |
| Cross-document | 10 |
| Entity-specific | 9 |
| Multi-hop | 6 |

### Vector Baseline Results

| Metric | Score |
|---|---|
| Recall@10 | 95.3% |
| Citation Precision | 74.0% |
| Abstention Accuracy | 87.3% |
| Unsupported Claim Rate | 12.7% |
| Answer F1 | 48.8% |
| Multihop Recall@10 | 74.1% |

### Hybrid Results

| Metric | Score |
|---|---|
| Recall@10 | 95.8% |
| Citation Precision | 74.6% |
| Abstention Accuracy | 88.6% |
| Unsupported Claim Rate | 12.7% |
| Answer F1 | 49.0% |
| Graph Contribution Rate | **31.4%** |
| Multihop Recall@10 | 74.9% |

### Key Finding

Hybrid retrieval contributes graph-sourced evidence in **31.4% of responses** while maintaining identical answer quality across all other metrics. The graph layer is additive — it expands evidence coverage without degrading semantic retrieval performance.

To reproduce evaluation:
```bash
# Run queries
python scripts/run_queries.py --mode vector_v2 --collection-id <id> --output-log storage/logs/query_log_vector.jsonl

# Run eval
python scripts/run_eval.py --retrieval-mode vector_v2 --gold-path storage/eval/gold/baseline_gold.jsonl --query-log-path storage/logs/query_log_vector.jsonl

# Generate dashboard
python scripts/generate_dashboard.py --open
```

---

## Features

- **Two retrieval modes** — vector-only and hybrid, selectable per collection at upload time
- **Citation tooltips** — hover over `[1]` `[2]` citations to preview source chunk text
- **Abstention enforcement** — returns `"Not found in documents."` rather than hallucinating
- **Embedding cache** — SQLite-backed content-addressed cache avoids redundant model calls
- **Live metrics sidebar** — shows retrieval stats, graph nodes, embedding avoidance rate
- **Evaluation dashboard** — full vector vs hybrid comparison with charts at `/eval/dashboard`
- **Persistent chat memory** — conversation history survives page refresh
- **Append-safe uploads** — add documents to an existing collection without reprocessing
- **Content-addressed IDs** — SHA-256 based document and chunk IDs ensure reproducibility

---

## Author

**Vetrivel Maheswaran**
M.S. Information Technology and Analytics — Rochester Institute of Technology
vm6923@rit.edu