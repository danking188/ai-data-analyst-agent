from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_idempotency_key
from app.api.request_context import get_request_id
from app.api.schemas import (
    AssistantConfirmationRequest,
    AssistantConversation,
    AssistantConversationCreate,
    AssistantConversationPage,
    AssistantConversationUpdate,
    AssistantFeedback,
    AssistantFeedbackRequest,
    AssistantMessage,
    AssistantMessageCreate,
    AssistantMessagePage,
    AssistantMetrics,
    AssistantToolCall,
    AssistantToolCallUpdate,
    AssistantTurnAccepted,
)
from app.core.config import Settings, get_settings
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.assistant import AssistantService
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.workers.assistant import process_assistant_turn_job
from app.workers.dispatch import schedule_job

router = APIRouter(prefix="/projects/{project_id}/assistant", tags=["Assistant"])


@router.get(
    "/metrics",
    response_model=AssistantMetrics,
    operation_id="getAssistantMetrics",
)
def get_metrics(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    window_days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> AssistantMetrics:
    return AssistantService(session, settings).metrics(
        project_id,
        subject_id=principal.subject_id,
        window_days=window_days,
    )


@router.patch(
    "/tool-calls/{tool_call_id}",
    response_model=AssistantToolCall,
    operation_id="updateAssistantToolCall",
)
def update_tool_call(
    project_id: str,
    tool_call_id: str,
    payload: AssistantToolCallUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantToolCall:
    with UnitOfWork(session):
        return AssistantService(session, settings).update_tool_call(
            project_id,
            tool_call_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )


@router.get(
    "/conversations",
    response_model=AssistantConversationPage,
    operation_id="listAssistantConversations",
)
def list_conversations(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AssistantConversationPage:
    return AssistantService(session, settings).list_conversations(
        project_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/conversations",
    response_model=AssistantConversation,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAssistantConversation",
)
def create_conversation(
    project_id: str,
    payload: AssistantConversationCreate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AssistantConversation:
    path = f"/api/v1/projects/{project_id}/assistant/conversations"
    request_hash = canonical_request_hash(payload.model_dump(mode="json"))
    idempotency = IdempotencyService(IdempotencyRepository(session))
    with UnitOfWork(session):
        replay = idempotency.replay_or_none(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return AssistantConversation.model_validate(replay)
        result = AssistantService(session, settings).create_conversation(
            project_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="assistant_conversation",
            resource_id=result.conversation_id,
            response_status=201,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.get(
    "/conversations/{conversation_id}",
    response_model=AssistantConversation,
    operation_id="getAssistantConversation",
)
def get_conversation(
    project_id: str,
    conversation_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantConversation:
    return AssistantService(session, settings).get_conversation(
        project_id, conversation_id, subject_id=principal.subject_id
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=AssistantConversation,
    operation_id="updateAssistantConversation",
)
def update_conversation(
    project_id: str,
    conversation_id: str,
    payload: AssistantConversationUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantConversation:
    with UnitOfWork(session):
        return AssistantService(session, settings).update_conversation(
            project_id,
            conversation_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=AssistantMessagePage,
    operation_id="listAssistantMessages",
)
def list_messages(
    project_id: str,
    conversation_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AssistantMessagePage:
    return AssistantService(session, settings).list_messages(
        project_id,
        conversation_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AssistantTurnAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createAssistantMessage",
)
def create_message(
    project_id: str,
    conversation_id: str,
    payload: AssistantMessageCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AssistantTurnAccepted:
    path = f"/api/v1/projects/{project_id}/assistant/conversations/{conversation_id}/messages"
    request_hash = canonical_request_hash(payload.model_dump(mode="json"))
    idempotency = IdempotencyService(IdempotencyRepository(session))
    replayed = False
    with UnitOfWork(session):
        replay = idempotency.replay_or_none(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            result = AssistantTurnAccepted.model_validate(replay)
            replayed = True
        else:
            result = AssistantService(session, settings).create_turn(
                project_id,
                conversation_id,
                payload,
                subject_id=principal.subject_id,
                request_id=get_request_id(request),
            )
            idempotency.record(
                subject_id=principal.subject_id,
                method=request.method,
                path=path,
                key=idempotency_key,
                request_hash=request_hash,
                resource_type="assistant_message",
                resource_id=result.assistant_message.message_id,
                response_status=202,
                response_json=result.model_dump(mode="json"),
            )
    if not replayed and result.job:
        schedule_job(background_tasks, process_assistant_turn_job, result.job.job_id)
    return result


@router.post(
    "/messages/{message_id}/confirm",
    response_model=AssistantTurnAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="confirmAssistantPlan",
)
def confirm_plan(
    project_id: str,
    message_id: str,
    payload: AssistantConfirmationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AssistantTurnAccepted:
    path = f"/api/v1/projects/{project_id}/assistant/messages/{message_id}/confirm"
    request_hash = canonical_request_hash(payload.model_dump(mode="json"))
    result, replayed = _idempotent_turn_action(
        session=session,
        settings=settings,
        principal=principal,
        request=request,
        path=path,
        key=idempotency_key,
        request_hash=request_hash,
        action=lambda service: service.confirm_plan(
            project_id,
            message_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        ),
    )
    if not replayed and result.job:
        schedule_job(background_tasks, process_assistant_turn_job, result.job.job_id)
    return result


@router.post(
    "/messages/{message_id}/retry",
    response_model=AssistantTurnAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="retryAssistantMessage",
)
def retry_message(
    project_id: str,
    message_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AssistantTurnAccepted:
    path = f"/api/v1/projects/{project_id}/assistant/messages/{message_id}/retry"
    request_hash = canonical_request_hash({"message_id": message_id})
    result, replayed = _idempotent_turn_action(
        session=session,
        settings=settings,
        principal=principal,
        request=request,
        path=path,
        key=idempotency_key,
        request_hash=request_hash,
        action=lambda service: service.retry_message(
            project_id,
            message_id,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        ),
    )
    if not replayed and result.job:
        schedule_job(background_tasks, process_assistant_turn_job, result.job.job_id)
    return result


@router.post(
    "/messages/{message_id}/cancel",
    response_model=AssistantMessage,
    operation_id="cancelAssistantMessage",
)
def cancel_message(
    project_id: str,
    message_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AssistantMessage:
    path = f"/api/v1/projects/{project_id}/assistant/messages/{message_id}/cancel"
    request_hash = canonical_request_hash({"message_id": message_id})
    idempotency = IdempotencyService(IdempotencyRepository(session))
    with UnitOfWork(session):
        replay = idempotency.replay_or_none(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return AssistantMessage.model_validate(replay)
        result = AssistantService(session, settings).cancel_message(
            project_id,
            message_id,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="assistant_message",
            resource_id=message_id,
            response_status=200,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.post(
    "/messages/{message_id}/feedback",
    response_model=AssistantFeedback,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAssistantFeedback",
)
def create_feedback(
    project_id: str,
    message_id: str,
    payload: AssistantFeedbackRequest,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AssistantFeedback:
    path = f"/api/v1/projects/{project_id}/assistant/messages/{message_id}/feedback"
    request_hash = canonical_request_hash(payload.model_dump(mode="json"))
    idempotency = IdempotencyService(IdempotencyRepository(session))
    with UnitOfWork(session):
        replay = idempotency.replay_or_none(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return AssistantFeedback.model_validate(replay)
        result = AssistantService(session, settings).create_feedback(
            project_id,
            message_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="assistant_feedback",
            resource_id=result.feedback_id,
            response_status=201,
            response_json=result.model_dump(mode="json"),
        )
        return result


def _idempotent_turn_action(
    *,
    session: Session,
    settings: Settings,
    principal: Principal,
    request: Request,
    path: str,
    key: str,
    request_hash: str,
    action: Callable[[AssistantService], AssistantTurnAccepted],
) -> tuple[AssistantTurnAccepted, bool]:
    idempotency = IdempotencyService(IdempotencyRepository(session))
    with UnitOfWork(session):
        replay = idempotency.replay_or_none(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=key,
            request_hash=request_hash,
        )
        if replay is not None:
            return AssistantTurnAccepted.model_validate(replay), True
        result = action(AssistantService(session, settings))
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=key,
            request_hash=request_hash,
            resource_type="assistant_message",
            resource_id=result.assistant_message.message_id,
            response_status=202,
            response_json=result.model_dump(mode="json"),
        )
        return result, False
