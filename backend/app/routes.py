from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, Query, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from .config import settings
from .observability import get_logger, log_event
from .rag.pipeline import RagPipeline
from pydantic import BaseModel
from .schemas import HistoryItem, HistoryResponse, QueryRequest, UploadResponse, DocumentStatusResponse
from .services.document_service import DocumentService

router = APIRouter(prefix="/api", tags=["decision-engine"])
logger = get_logger("api")

class EvaluateRequest(BaseModel):
    question: str
    answer: str
    context: str = ""
    
class EvaluateResponse(BaseModel):
    relevance: str
    faithfulness: str
    groundedness: str
    reasoning: str

@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_answer(payload: EvaluateRequest) -> EvaluateResponse:
    from langchain.evaluation import load_evaluator
    from langchain_openai import ChatOpenAI
    from .config import settings
    
    start = time.perf_counter()
    eval_llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0
    )
    
    rel_eval = load_evaluator("criteria", criteria={"relevance": "Does the response directly answer the specific question asked by the user?"}, llm=eval_llm)
    acc_eval = load_evaluator("labeled_criteria", criteria={"faithfulness": "Is the response factually accurate based strictly on the provided reference context?"}, llm=eval_llm)
    grnd_eval = load_evaluator(
        "labeled_criteria", 
        criteria={"groundedness": "Does the response avoid hallucinating external information not present in the reference context?"},
        llm=eval_llm
    )
    
    rel_result = rel_eval.evaluate_strings(prediction=payload.answer, input=payload.question)
    acc_result = acc_eval.evaluate_strings(prediction=payload.answer, input=payload.question, reference=payload.context)
    grnd_result = grnd_eval.evaluate_strings(prediction=payload.answer, input=payload.question, reference=payload.context)

    response = EvaluateResponse(
        relevance=rel_result.get("value", "N/A"),
        faithfulness=acc_result.get("value", "N/A"),
        groundedness=grnd_result.get("value", "N/A"),
        reasoning=f"Relevance: {rel_result.get('reasoning')} \n\nAccuracy: {acc_result.get('reasoning')} \n\nGroundedness: {grnd_result.get('reasoning')}"
    )
    log_event(
        logger,
        "answer_evaluated",
        latency_ms=round((time.perf_counter() - start) * 1000),
        question_preview=payload.question[:120],
        answer_chars=len(payload.answer),
        context_chars=len(payload.context),
        relevance=response.relevance,
        faithfulness=response.faithfulness,
        groundedness=response.groundedness,
    )
    return response



def get_document_service() -> DocumentService:
    return DocumentService()


def get_rag_pipeline() -> RagPipeline:
    return RagPipeline()


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_service: DocumentService = Depends(get_document_service),
) -> UploadResponse:
    record = await document_service.save_upload_initial(file)
    background_tasks.add_task(document_service.process_upload_background, record.id, record.storage_path, record.filename)
    log_event(
        logger,
        "upload_enqueued",
        document_id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        status=record.status,
    )
    return UploadResponse(
        document_id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        chunk_count=0,
        uploaded_at=record.uploaded_at,
        status=record.status
    )


@router.get("/documents/{doc_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    doc_id: int,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentStatusResponse:
    record = document_service.repository.get(doc_id)
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")
    chunk_records = document_service.chunk_repository.list_for_retrieval(doc_id)
    log_event(
        logger,
        "document_status_checked",
        document_id=doc_id,
        status=record.status,
        chunk_count=len(chunk_records),
    )
    return DocumentStatusResponse(
        status=record.status,
        chunk_count=len(chunk_records)
    )


@router.post("/query")
async def query_documents(
    payload: QueryRequest,
    rag_pipeline: RagPipeline = Depends(get_rag_pipeline),
) -> StreamingResponse:
    log_event(
        logger,
        "query_requested",
        question_preview=payload.question[:160],
        doc_id=payload.doc_id,
        top_k=payload.top_k,
        chat_history_messages=len(payload.chat_history or []),
    )
    return StreamingResponse(
        rag_pipeline.stream_rag_response(
            query=payload.question,
            doc_id=payload.doc_id,
            top_k=payload.top_k,
            chat_history=payload.chat_history,
        ),
        media_type="text/event-stream",
    )


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    limit: int = Query(default=20, ge=1, le=settings.max_history_limit),
    rag_pipeline: RagPipeline = Depends(get_rag_pipeline),
) -> HistoryResponse:
    records = rag_pipeline.list_history(limit)
    items = [
        HistoryItem(
            id=record.id,
            query=record.query,
            answer=record.answer,
            reasoning=record.reasoning,
            sources=record.sources,
            retrieval_latency_ms=record.retrieval_latency_ms,
            chunk_count=record.chunk_count,
            matched_document_ids=record.matched_document_ids,
            matched_chunk_ids=record.matched_chunk_ids,
            raw_response=record.raw_response,
            created_at=record.created_at,
        )
        for record in records
    ]
    response = HistoryResponse(items=items, count=len(items))
    log_event(logger, "history_requested", limit=limit, count=response.count)
    return response
