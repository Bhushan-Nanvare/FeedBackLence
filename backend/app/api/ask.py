from fastapi import APIRouter, HTTPException, status

from app.ai.answering import answer_question
from app.api.deps import EmbedderDep, LLMDep, ReadableWorkspaceDep, SessionDep
from app.api.schemas import (
    AnswerRead,
    AskRequest,
    CitedItemRead,
    FeedbackItemRead,
    QuestionRead,
    RatingUpdate,
)
from app.errors import RateLimitedError
from app.models import Question
from app.search.hybrid import SearchFilters

router = APIRouter(prefix="/workspaces/{slug}", tags=["ask"])


@router.post("/ask", response_model=AnswerRead)
def ask(
    body: AskRequest,
    # Asking only reads feedback, so anyone who may read the workspace may ask.
    workspace: ReadableWorkspaceDep,
    session: SessionDep,
    embedder: EmbedderDep,
    llm: LLMDep,
) -> AnswerRead:
    """Answer a question using only this workspace's feedback, citing the reports used."""
    try:
        answer = answer_question(
            session,
            workspace,
            body.question,
            llm,
            embedder,
            snippets=body.snippets,
            filters=SearchFilters(
                type=body.type,
                area=body.area,
                state=body.state,
                created_after=body.created_after,
                created_before=body.created_before,
                include_maintainer=body.include_maintainer,
            ),
        )
    except RateLimitedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None

    return AnswerRead(
        question_id=answer.question_id,
        question=body.question,
        answer=answer.text,
        enough_evidence=answer.enough_evidence,
        considered_count=len(answer.considered_items),
        sources=[
            CitedItemRead(number=cited.number, item=FeedbackItemRead.model_validate(cited.item))
            for cited in answer.cited
        ],
        dropped_citations=answer.dropped_citations,
    )


@router.post("/questions/{question_id}/rating", response_model=QuestionRead)
def rate_answer(
    question_id: int, body: RatingUpdate, workspace: ReadableWorkspaceDep, session: SessionDep
) -> Question:
    """Record whether an answer helped, which is the signal for improving the prompt."""
    question = session.get(Question, question_id)
    if question is None or question.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    question.helpful = body.helpful
    session.commit()
    return question
