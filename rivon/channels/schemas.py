"""API shapes for the channels module. Never exposes a token, sealed or not."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from rivon.channels.messages import Channel
from rivon.channels.models import ConnectionStatus


class ConnectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    provider: Channel
    external_id: str
    display_name: str | None
    status: ConnectionStatus
    status_detail: str | None
    granted_scopes: list[str]
    expires_at: datetime | None
    connected_at: datetime
    #: True when the customer has to reconnect before this works again.
    needs_attention: bool


class ConnectStartOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Where to send the customer. Carries the single-use state.
    authorize_url: str


class ConnectCallbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=16, max_length=64)


class SkippedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str
    reason: str


class ConnectOutcomeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connected: list[ConnectionOut]
    skipped: list[SkippedOut]
