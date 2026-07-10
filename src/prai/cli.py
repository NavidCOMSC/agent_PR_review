from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    NotRequired,
    TypedDict,
    Annotated,
    Any,
)
import functools
import inspect

import anyio.from_thread
import anyio.to_thread
import anyio.abc
import anyio
import pydantic
import typer

import prai.azure_devops
import prai.claude_code
import prai.llm_lounge
import prai.git

import prai.commands

if TYPE_CHECKING:
    from collections.abc import (
        Container,
        Awaitable,
        Mapping,
    )


__all__ = [
    "app",
]

app = typer.Typer(
    rich_markup_mode="rich",
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)

blocking_portal_provider: anyio.from_thread.BlockingPortalProvider = (
    anyio.from_thread.BlockingPortalProvider()
)


class State(TypedDict):
    working_directory: pydantic.DirectoryPath
    pull_request: prai.azure_devops.PullRequest
    llm_lounge: prai.llm_lounge.Lounge
    claude_code: prai.claude_code.ClaudeCode
    git: prai.git.Git

    temporary_directory: NotRequired[anyio.TemporaryDirectory]


def get_command_required_state_keys(
    command: callable[[Any, ...], Awaitable[Any]],
    state_keys: Container[str],
) -> list[str]:
    signature: inspect.Signature = inspect.signature(command)
    return [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.name in state_keys
        and (
            parameter.kind == parameter.POSITIONAL_OR_KEYWORD
            or parameter.kind == parameter.KEYWORD_ONLY
        )
    ]


async def clear_directory(
    directory: pydantic.DirectoryPath,
) -> None:
    directory_path: anyio.Path = anyio.Path(
        directory,
    )

    if not await directory_path.exists():
        return

    async for child_path in directory_path.iterdir():
        if await child_path.is_dir():
            await clear_directory(child_path)
        else:
            await child_path.unlink()

    await directory_path.rmdir()


def run_command(
    command: callable[[Any, ...], Awaitable[Any]],
    ctx: typer.Context,
) -> Any:
    required_state_keys: list[str] = get_command_required_state_keys(
        command=command,
        state_keys=ctx.obj,
    )

    arguments: dict[str, Any] = {
        key: value
        for key, value in ctx.obj.items()
        if key in required_state_keys
    }

    task: callable[[], Awaitable[Any]] = functools.partial(
        command,
        **arguments,
    )

    async def task_function() -> Any:
        result: Any = await command(**arguments)
        await cleanup()

    with blocking_portal_provider as blocking_portal:
        blocking_portal.call(task)


def map_result(
    async_function: callable[[Any, ...], Awaitable[Any]],
    mapping: Mapping[str, Any],
    key: str,
) -> callable[[Any, ...], Awaitable[Any]]:
    @functools.wraps(async_function)
    async def wrapped(
        *args: Any,
        **kwargs: Any,
    ) -> Awaitable[Any]:
        result: Any = await async_function(*args, **kwargs)
        mapping[key] = result
        return result

    return wrapped


async def create_working_directory() -> pydantic.DirectoryPath:
    temporary_directory_path: str = await anyio.mkdtemp(
        prefix="prai_",
    )
    return pydantic.DirectoryPath(temporary_directory_path)


async def create_state(
    state: dict[str, Any] | None = None,
    **options,
) -> State:
    state = state or {}

    map_result_to_state = functools.partial(
        map_result,
        mapping=state,
    )

    init_pull_request = map_result_to_state(
        prai.azure_devops.PullRequest.from_url,
        key="pull_request",
    )
    init_git = map_result_to_state(
        prai.git.Git.from_executable,
        key="git",
    )
    init_llm_lounge = map_result_to_state(
        prai.llm_lounge.Lounge.from_url,
        key="llm_lounge",
    )

    async def create_claude_code(
        url: pydantic.HttpUrl,
        api_key: prai.llm_lounge.APIKey,
        **claude_arguments: Any,
    ) -> prai.claude_code.ClaudeCode:
        lounge: prai.llm_lounge.Lounge
        lounge = await init_llm_lounge(
            url=url,
            api_key=api_key,
        )

        return await prai.claude_code.ClaudeCode.from_llm_lounge(
            llm_lounge=lounge,
            **claude_arguments,
        )

    init_claude_code = map_result_to_state(
        create_claude_code,
        key="claude_code",
    )

    task_group: anyio.abc.TaskGroup = anyio.create_task_group()

    state["working_directory"] = await create_working_directory()

    tasks = [
        functools.partial(
            init_pull_request,
            url=options.get("azure_devops_pull_request_url"),
            access_token=options.get("azure_devops_access_token"),
        ),
        functools.partial(
            init_claude_code,
            url=options.get("llm_lounge_url"),
            api_key=options.get("llm_lounge_api_key"),
            default_model=options.get("claude_default_model"),
            opus_model=options.get("claude_opus_model"),
            sonnet_model=options.get("claude_sonnet_model"),
            haiku_model=options.get("claude_haiku_model"),
            subagent_model=options.get("claude_subagent_model"),
            small_fast_model=options.get("claude_small_fast_model"),
            experimental_betas=options.get("claude_experimental_betas"),
        ),
        functools.partial(
            init_git,
            executable=options.get("git_executable"),
        ),
    ]

    async with task_group:
        for task in tasks:
            task_group.start_soon(task)

    return State(**state)


@app.callback()
def callback(
    ctx: typer.Context,
    azure_devops_pull_request_url: Annotated[
        pydantic.HttpUrl,
        typer.Option(
            "--pull-request-url",
            "--pr",
            envvar=[
                "PULL_REQUEST_URL",
            ],
            parser=pydantic.HttpUrl,
        ),
    ] = ...,
    azure_devops_access_token: Annotated[
        prai.azure_devops.AccessToken,
        typer.Option(
            "--azure-devops-token",
            envvar=[
                "AZURE_DEVOPS_TOKEN",
            ],
        ),
    ] = ...,
    llm_lounge_url: Annotated[
        pydantic.HttpUrl,
        typer.Option(
            "--claude-proxy-url",
            "--llm-lounge-url",
            envvar=[
                "CLAUDE_PROXY_URL",
                "ANTHROPIC_BASE_URL",
                "LLM_LOUNGE_URL",
            ],
            parser=pydantic.HttpUrl,
        ),
    ] = ...,
    llm_lounge_api_key: Annotated[
        prai.llm_lounge.APIKey,
        typer.Option(
            "--claude-proxy-api-key",
            "--llm-lounge-api-key",
            envvar=[
                "CLAUDE_PROXY_API_KEY",
                "ANTHROPIC_AUTH_TOKEN",
                "LLM_LOUNGE_API_KEY",
            ],
        ),
    ] = ...,
    claude_default_model: Annotated[
        prai.claude_code.ModelName,
        typer.Option(
            "--claude-default-model",
            envvar=[
                "CLAUDE_DEFAULT_MODEL",
                "ANTHROPIC_DEFAULT_MODEL",
                "ANTHROPIC_MODEL",
            ],
        ),
    ] = ...,
    claude_opus_model: Annotated[
        prai.claude_code.ModelName,
        typer.Option(
            "--claude-opus-model",
            envvar=[
                "CLAUDE_OPUS_MODEL",
                "CLAUDE_DEFAULT_OPUS_MODEL",
                "ANTHROPIC_OPUS_MODEL",
                "ANTHROPIC_DEFAULT_OPUS_MODEL",
            ],
        ),
    ] = ...,
    claude_sonnet_model: Annotated[
        prai.claude_code.ModelName,
        typer.Option(
            "--claude-sonnet-model",
            envvar=[
                "CLAUDE_SONNET_MODEL",
                "CLAUDE_DEFAULT_SONNET_MODEL",
                "ANTHROPIC_SONNET_MODEL",
                "ANTHROPIC_DEFAULT_SONNET_MODEL",
            ],
        ),
    ] = ...,
    claude_haiku_model: Annotated[
        prai.claude_code.ModelName,
        typer.Option(
            "--claude-haiku-model",
            envvar=[
                "CLAUDE_HAIKU_MODEL",
                "CLAUDE_DEFAULT_HAIKU_MODEL",
                "ANTHROPIC_HAIKU_MODEL",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            ],
        ),
    ] = ...,
    claude_subagent_model: Annotated[
        prai.claude_code.ModelName,
        typer.Option(
            "--claude-subagent-model",
            envvar=[
                "CLAUDE_SUBAGENT_MODEL",
                "ANTHROPIC_SUBAGENT_MODEL",
            ],
        ),
    ] = ...,
    claude_small_fast_model: Annotated[
        prai.claude_code.ModelName,
        typer.Option(
            "--claude-small-fast-model",
            envvar=[
                "CLAUDE_SMALL_FAST_MODEL",
                "ANTHROPIC_SMALL_FAST_MODEL",
            ],
        ),
    ] = ...,
    claude_experimental_betas: Annotated[
        prai.claude_code.ExperimentalBetas,
        typer.Option(
            "--claude-experimental-betas",
            envvar=[
                "CLAUDE_EXPERIMENTAL_BETAS",
            ],
        ),
    ] = prai.claude_code.ExperimentalBetas.DISABLED,
    git_executable: Annotated[
        str,
        typer.Option(
            "--git-executable",
            envvar=[
                "GIT_EXECUTABLE",
            ],
        ),
    ] = "git",
) -> None:
    setup: callable[[], Awaitable[State]] = functools.partial(
        create_state,
        azure_devops_pull_request_url=azure_devops_pull_request_url,
        azure_devops_access_token=azure_devops_access_token,
        llm_lounge_url=llm_lounge_url,
        llm_lounge_api_key=llm_lounge_api_key,
        claude_default_model=claude_default_model,
        claude_opus_model=claude_opus_model,
        claude_sonnet_model=claude_sonnet_model,
        claude_haiku_model=claude_haiku_model,
        claude_subagent_model=claude_subagent_model,
        claude_small_fast_model=claude_small_fast_model,
        claude_experimental_betas=claude_experimental_betas,
        git_executable=git_executable,
    )
    with blocking_portal_provider as blocking_portal:
        ctx.obj = blocking_portal.call(setup)


async def cleanup(
    ctx: typer.Context,
) -> None:
    working_directory: pydantic.DirectoryPath | None = ctx.obj.get(
        "working_directory", None
    )

    if working_directory:
        await clear_directory(working_directory)


@app.command()
def review(
    ctx: typer.Context,
) -> None:
    run_command(prai.commands.review, ctx=ctx)
