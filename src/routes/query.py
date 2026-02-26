from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.config import get_settings
from src.eval.logger import EvalLogger
from src.llm.client import LLMClient  
from src.llm.openai_client import OpenAIClient 
from src.retrieval.vector_retriever import VectorRetriever
from src.services.query_service import QueryService

router = APIRouter(tags=["query"])


class QueryIn(BaseModel):
    collection_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)


@router.post("/query")
def query(inp: QueryIn):
    s = get_settings()

    try:
        llm: LLMClient = OpenAIClient.from_env()  # or your actual LLM impl
        retriever = VectorRetriever(s=s)
        logger = EvalLogger(log_path=s.query_log_path)

        service = QueryService(
            llm=llm,
            retriever=retriever,
            logger=logger,
        )

        return service.run(
            collection_id=inp.collection_id,
            question=inp.question,
            chat_history=[],
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")