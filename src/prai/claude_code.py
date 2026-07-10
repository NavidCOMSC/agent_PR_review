from __future__ import annotations

import claude_agent_sdk
import pydantic
import anyio

from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
)
import pathlib
import os

import prai.llm_lounge

if TYPE_CHECKING:
    from typing import Self


__all__ = [
    "APIKey",
    "ModelName",
    "ExperimentalBetas",
    "ClaudeCode",
]


APIKey = prai.llm_lounge.APIKey


ModelName = Annotated[
    str,
    pydantic.StringConstraints(
        strip_whitespace=True,
        pattern=r"^(eu|global)\.anthropic\.claude-(sonnet|haiku|opus)-\d-\d.*",
    ),
]


class ExperimentalBetas(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ClaudeCode:
    def __init__(
        self: Self,
        base_url: pydantic.HttpUrl,
        api_key: APIKey,
        *,
        default_model: ModelName,
        opus_model: ModelName,
        sonnet_model: ModelName,
        haiku_model: ModelName,
        subagent_model: ModelName,
        small_fast_model: ModelName,
        experimental_betas: ExperimentalBetas,
    ):
        self.base_url = base_url
        self.api_key = api_key

        self.default_model = default_model
        self.opus_model = opus_model
        self.sonnet_model = sonnet_model
        self.haiku_model = haiku_model
        self.subagent_model = subagent_model
        self.small_fast_model = small_fast_model

        self.experimental_betas = experimental_betas

    async def get_options(
        self: Self,
        *,
        working_directory: pydantic.DirectoryPath,
    ) -> claude_agent_sdk.ClaudeAgentOptions:
        environment_variables: dict[str, Any] = {
            "ANTHROPIC_BASE_URL": self.base_url,
            "ANTHROPIC_AUTH_TOKEN": self.api_key,
            "ANTHROPIC_MODEL": self.default_model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": self.opus_model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": self.sonnet_model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": self.haiku_model,
            "ANTHROPIC_SUBAGENT_MODEL": self.subagent_model,
            "ANTHROPIC_SMALL_FAST_MODEL": self.small_fast_model,
            "ANTHROPIC_DISABLE_EXPERIMENTAL_BETAS": (
                "1"
                if self.experimental_betas == ExperimentalBetas.DISABLED
                else "0"
            ),
        }
        environment_variables: dict[str, str] = {
            key: str(value) for key, value in environment_variables.items()
        }

        return claude_agent_sdk.ClaudeAgentOptions(
            cwd=working_directory or await anyio.Path.cwd(),
            setting_sources=["project"],
            allowed_tools=[
                "Task",
                "Read",
                "Glob",
                "Grep",
                "Bash(git diff *)",
                "Bash(git log *)",
            ],
        )

    async def get_agent(
        self: Self,
        **kwargs: Any,
    ) -> claude_agent_sdk.ClaudeSDKClient:
        return claude_agent_sdk.ClaudeSDKClient(
            options=await self.get_options(**kwargs),
        )

    @classmethod
    async def from_llm_lounge(
        cls,
        llm_lounge: prai.llm_lounge.Lounge,
        *,
        default_model: ModelName,
        opus_model: ModelName,
        sonnet_model: ModelName,
        haiku_model: ModelName,
        subagent_model: ModelName,
        small_fast_model: ModelName,
        experimental_betas: ExperimentalBetas,
    ) -> ClaudeCode:
        return cls(
            base_url=llm_lounge.url,
            api_key=llm_lounge.api_key,
            default_model=default_model,
            opus_model=opus_model,
            sonnet_model=sonnet_model,
            haiku_model=haiku_model,
            subagent_model=subagent_model,
            small_fast_model=small_fast_model,
            experimental_betas=experimental_betas,
        )
