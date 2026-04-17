from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.config import get_settings
from src.eval.logger import EvalLogger
from src.llm.client import LLMClient  
from src.llm.openai_client import OpenAIClient 
from src.retrieval.vector_retriever import VectorRetriever
from src.retrieval.graph_retriever import GraphRetriever
from src.retrieval.hybrid_retriever import HybridRetriever
from src.services.query_service import QueryService, QueryServiceConfig

router = APIRouter(tags=["query"])


class QueryIn(BaseModel):
    collection_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    retrieval_mode: str | None = None 
    chat_history: list[dict] = Field(default_factory=list)


@router.post("/query")
def query(inp: QueryIn):
    s = get_settings()

    try:
        llm: LLMClient = OpenAIClient.from_env()  
        retriever = VectorRetriever(s=s)
        graph_retriever = GraphRetriever(s=s)
        hybrid_retriever = HybridRetriever(
            vector_weight=s.retrieval.hybrid_vector_weight,
            graph_weight=s.retrieval.hybrid_graph_weight,
        )
        logger = EvalLogger(log_path=s.query_log_path)

        service = QueryService(
           llm=llm,
            retriever=retriever,
            graph_retriever=graph_retriever,
            hybrid_retriever=hybrid_retriever,
            logger=logger,
            cfg=QueryServiceConfig(
                top_k=s.retrieval.top_k,
                max_context_chunks=s.retrieval.max_context_chunks,
                rerank_enabled=s.retrieval.rerank_enabled,
            ),
        )

        return service.run(
            collection_id=inp.collection_id,
            question=inp.question,
            chat_history=inp.chat_history,
            retrieval_mode=inp.retrieval_mode,
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")