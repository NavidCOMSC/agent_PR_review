from __future__ import annotations

from typing import Annotated, Self
from enum import StrEnum

import pydantic


__all__ = [
    "APIKey",
    "LLMLounge",
]


APIKey = Annotated[
    str,
    pydantic.StringConstraints(
        pattern="^sk-[a-zA-Z0-9-]{22}$",
        strip_whitespace=True,
    ),
]


class EnvironmentType(StrEnum):
    DEVELOPMENT = "devlopment"
    TESTING = "testing"
    PRODUCTION = "production"


class InterfaceType(StrEnum):
    LLM_LOUNGE = "llm-lounge"
    LLM_LOUNGE_N = "llm-lounge-n"


def create_llm_lounge_url_format_error(
    url: pydantic.HttpUrl,
) -> ValueError:
    issue: str = "LLM Lounge URL in unexpected format."
    expected: str = " OR ".join(
        [
            "https://capi.zurich.com/",
            "https://test.capi.zurich.com/",
            "https://genai-lounge-nx-litellm-emea.zurich.com/",
            "https://genai-lounge-nx-litellm-{environment}-emea.zurich.com/",
        ]
    )
    got: str = str(url)
    message: str = f"{issue}\nExpected: {expected}\nGot: {got}"

    return ValueError(message)


class Lounge:
    def __init__(
        self: Self,
        url: pydantic.HttpUrl,
        interface_type: InterfaceType,
        environment_type: EnvironmentType,
        api_key: APIKey,
    ) -> None:
        self.url = url
        self.api_key = api_key

        self.interface_type = interface_type
        self.environment_type = environment_type

    @classmethod
    async def from_fields(
        cls: type[Self],
        api_key: APIKey,
        interface_type: InterfaceType,
        environment_type: EnvironmentType | None = None,
    ) -> Self:
        url: pydantic.HttpUrl

        if interface_type == InterfaceType.LLM_LOUNGE:
            url = pydantic.HttpUrl(
                "https://test.capi.zurich.com"
                if environment_type != EnvironmentType.PRODUCTION
                else "https://capi.zurich.com"
            )
        else:
            environment: str | None = (
                "dev"
                if environment_type == EnvironmentType.DEVELOPMENT
                else "uat"
                if environment_type == EnvironmentType.TESTING
                else "prod"
                if environment_type == EnvironmentType.PRODUCTION
                else None
            )

            url = pydantic.HttpUrl(
                "https://genai-lounge-nx-litellm-emea.zurich.com"
                if environment_type is None
                else f"https://genai-lounge-nx-litellm-{environment}-emea.zurich.com"
            )

        return cls(
            url=url,
            interface_type=interface_type,
            environment_type=environment_type or EnvironmentType.PRODUCTION,
            api_key=api_key,
        )

    @classmethod
    async def from_url(
        cls: type[Self],
        url: pydantic.HttpUrl,
        api_key: APIKey,
    ) -> Self:
        if not (url.host and url.host.endswith(".zurich.com")):
            url_format_error: ValueError = create_llm_lounge_url_format_error(
                url=url,
            )
            message: str = "LLM Lounge URL must exist in zurich.com domain."
            domain_error: ValueError = ValueError(message)
            raise url_format_error from domain_error

        subhost: str = url.host[: -len(".zurich.com")]
        interface_type: InterfaceType
        environment_type: EnvironmentType

        if subhost.endswith("capi"):
            interface_type = InterfaceType.LLM_LOUNGE
            environment_type = (
                EnvironmentType.TESTING
                if subhost.startswith("test")
                else EnvironmentType.PRODUCTION
            )
        else:
            interface_type = InterfaceType.LLM_LOUNGE_N
            match subhost.split("-"):
                case ["genai", "lounge", "nx", "litellm", environment, "emea"]:
                    environment_type = (
                        EnvironmentType.DEVELOPMENT
                        if environment == "dev"
                        else EnvironmentType.TESTING
                        if environment == "uat"
                        else EnvironmentType.PRODUCTION
                    )
                case ["genai", "lounge", "nx", "litellm", "emea"]:
                    environment_type = EnvironmentType.PRODUCTION

                case _:
                    url_format_error: ValueError = (
                        create_llm_lounge_url_format_error(
                            url=url,
                        )
                    )
                    raise url_format_error

        return await cls.from_fields(
            interface_type=interface_type,
            environment_type=environment_type,
            api_key=api_key,
        )
