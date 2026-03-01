from pydantic import BaseModel, Field
from enum import Enum


class SessionStatus(str, Enum):
    EXECUTING = "executing"
    WAITING = "waiting"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NEED_CONFIRM = "need_confirm"
    CANCELLED = "cancelled"
    STUCK = "stuck"


class ReportRequest(BaseModel):
    session_id: str | None = None
    project: str
    task: str
    previous_request: str = ""
    status: str = "completed"
    questions: list[str] = []
    timestamp: str = ""


class ReplyRequest(BaseModel):
    reply: str


class SessionPatch(BaseModel):
    status: str


class SessionResponse(BaseModel):
    session_id: str
    project: str
    task: str
    previous_request: str
    status: str
    questions: list[str]
    timestamp: str
    last_active: str
    reply: str | None = None
    reply_timestamp: str | None = None
    task_id: int | None = None


class ReportResponse(BaseModel):
    session_id: str
    task_id: int


class PollResponse(BaseModel):
    reply: str | None = None
    has_reply: bool = False


class KillPortRequest(BaseModel):
    port: int = Field(gt=0, le=65535)


class ServerConfig(BaseModel):
    name: str
    host: str
    port: int = 22
    path: str = ""
    key: str = ""


class ProjectSetup(BaseModel):
    path: str
    name: str
