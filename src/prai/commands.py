from __future__ import annotations

import claude_agent_sdk
import pydantic

import prai.azure_devops
import prai.claude_code
import prai.git


async def git_checkout_pull_request(
    git: prai.git.Git,
    pull_request: prai.azure_devops.PullRequest,
    working_directory: pydantic.DirectoryPath,
) -> pydantic.DirectoryPath:
    await git.clone(
        pull_request.repository_url,
        working_directory=working_directory,
    )

    repository_directory: pydantic.DirectoryPath = (
        working_directory / pull_request.repository
    )
    pull_request_branch: str = f"pull/{pull_request.pull_request_id}"

    await git.fetch(
        refspec=f"{pull_request_branch}/merge:{pull_request_branch}",
        working_directory=repository_directory,
    )
    await git.checkout(
        spec=pull_request_branch,
        working_directory=repository_directory,
    )

    return repository_directory


async def review(
    working_directory: pydantic.DirectoryPath,
    pull_request: prai.azure_devops.PullRequest,
    claude_code: prai.claude_code.ClaudeCode,
    git: prai.git.Git,
) -> None:
    repository_directory: pydantic.DirectoryPath
    repository_directory = await git_checkout_pull_request(
        git=git,
        pull_request=pull_request,
        working_directory=working_directory,
    )

    repository_agent: claude_agent_sdk.ClaudeSDKClient
    repository_agent = await claude_code.get_agent(
        working_directory=repository_directory,
    )

    async with repository_agent as claude:
        await claude.query(
            "You are a senior software engineer tasked with reviewing code quality. "
            + "Your role is to assess the code in a Git repository pull request and "
            + "comment on bugs, security issues, and code quality.\n\n"
            + "Today you are reviewing the following repository:\n\n"
            + f'Organisation: "{pull_request.organisation}"\n'
            + f'Project: "{pull_request.project}"\n'
            + f'Repository: "{pull_request.repository}"\n'
            + f'Source Branch: "{pull_request.api_model.source_ref_name}"\n'
            + f'Target Branch: "{pull_request.api_model.target_ref_name}"\n'
            + f"Pull Request ID: {pull_request.pull_request_id}\n\n"
            + "To review this pull request, you are running in a local Git repository "
            + f'with the remote branch "pull/{pull_request.pull_request_id}/merge" checked out to '
            + f'"pull/{pull_request.pull_request_id}".'
        )

        async for message in claude.receive_response():
            if isinstance(message, claude_agent_sdk.ResultMessage):
                print(message.result)
