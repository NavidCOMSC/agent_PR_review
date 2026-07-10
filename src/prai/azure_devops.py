from __future__ import annotations
from multiprocessing import Value

from typing import (
    TYPE_CHECKING,
    NotRequired,
    TypedDict,
    Annotated,
    Unpack,
    Self,
)
import urllib.parse
import functools

import azure.devops.connection
import msrest.authentication
import pydantic

if TYPE_CHECKING:
    import azure.devops.v7_1.git.git_client
    import azure.devops.v7_1.git.models


__all__ = [
    "PullRequestID",
]


AccessToken = Annotated[
    str,
    pydantic.StringConstraints(
        pattern="^[a-zA-Z0-9]{32,256}$",
        strip_whitespace=True,
    ),
]

OrganisationName = Annotated[
    str,
    pydantic.StringConstraints(
        pattern="^[a-zA-Z0-9][a-zA-Z0-9\-]{0,48}[a-zA-Z0-9]$",
        strip_whitespace=True,
    ),
]

ProjectName = Annotated[
    str,
    pydantic.StringConstraints(
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_\-\. ]{0,62}[a-zA-Z0-9_]$",
        strip_whitespace=True,
    ),
]

GitRepositoryName = Annotated[
    str,
    pydantic.StringConstraints(
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_\-\. ]{0,62}[a-zA-Z0-9_]$",
        strip_whitespace=True,
    ),
]

PullRequestID = Annotated[
    int,
    pydantic.Field(
        gt=0,
        lt=1_000_000,
        strict=True,
    ),
]


class Authentication(TypedDict):
    organisation: OrganisationName
    access_token: AccessToken


class PullRequestReference(TypedDict):
    organisation: OrganisationName
    pull_request_id: PullRequestID

    project: NotRequired[ProjectName | None]
    repository: NotRequired[GitRepositoryName | None]


@pydantic.validate_call
def create_pull_request_reference(
    organisation: OrganisationName,
    pull_request_id: PullRequestID,
    *,
    project: ProjectName | None = None,
    repository: GitRepositoryName | None = None,
) -> PullRequestReference:
    return PullRequestReference(
        organisation=organisation,
        pull_request_id=pull_request_id,
        project=project,
        repository=repository,
    )


def create_pull_request_url_format_error(
    url: pydantic.HttpUrl,
) -> ValueError:
    issue: str = "Pull request URL in unexpected format."
    expected: str = (
        "https://dev.azure.com/"
        + "{organisation}/{project}/"
        + "_git/{repository}/"
        + "pullrequest/{id}"
    )
    got: str = str(url)
    message: str = f"{issue}\nExpected: {expected}\nGot: {got}"

    return ValueError(message)


def create_pull_request_reference_from_url(
    url: pydantic.HttpUrl,
) -> PullRequestReference:
    if not url.path:
        error: ValueError = create_pull_request_url_format_error(url=url)
        raise error

    match url.path.split("/")[1:]:
        case [
            organisation_string,
            project_string,
            "_git",
            repository_string,
            "pullrequest",
            pull_request_id_string,
        ]:
            try:
                organisation_string = urllib.parse.unquote(organisation_string)
                project_string = urllib.parse.unquote(project_string)
                repository_string = urllib.parse.unquote(repository_string)
                pull_request_id_int: int = int(pull_request_id_string)
            except ValueError as conversion_error:
                url_format_error: ValueError = (
                    create_pull_request_url_format_error(
                        url=url,
                    )
                )
                raise url_format_error from conversion_error

            return create_pull_request_reference(
                organisation=organisation_string,
                project=project_string,
                repository=repository_string,
                pull_request_id=pull_request_id_int,
            )

        case _:
            error: ValueError = create_pull_request_url_format_error(url=url)
            raise error


@functools.lru_cache
def create_connection(
    **authentication: Unpack[Authentication],
) -> azure.devops.connection.Connection:
    organisation: OrganisationName
    organisation = authentication.get("organisation")
    access_token: AccessToken
    access_token = authentication.get("access_token")

    credentials = msrest.authentication.BasicAuthentication("", access_token)
    return azure.devops.connection.Connection(
        base_url=f"https://dev.azure.com/{organisation}",
        creds=credentials,
    )


class Resource:
    def __init__(
        self: Self,
        **authentication: Unpack[Authentication],
    ) -> None:
        self.organisation = authentication.get("organisation")
        self.access_token = authentication.get("access_token")

        self.connection: azure.devops.connection.Connection
        self.connection = create_connection(**authentication)


class PullRequest(Resource):
    def __init__(
        self: Self,
        api_model: azure.devops.v7_1.git.models.GitPullRequest,
        *,
        project: ProjectName,
        repository: GitRepositoryName,
        pull_request_id: PullRequestID,
        **authentication: Unpack[Authentication],
    ) -> None:
        super().__init__(**authentication)

        self.api_model = api_model

        self.project = project
        self.repository = repository
        self.pull_request_id = pull_request_id

    @property
    def repository_url(self) -> pydantic.HttpUrl:
        authentication: str = self.access_token
        organisation: str = urllib.parse.quote(self.organisation)
        project: str = urllib.parse.quote(self.project)
        repository: str = urllib.parse.quote(self.repository)

        url_string: str = "/".join(
            [
                f"https://{authentication}@dev.azure.com",
                organisation,
                project,
                "_git",
                repository,
            ]
        )

        return pydantic.HttpUrl(url_string)

    @classmethod
    async def from_url(
        cls: type[Self],
        url: pydantic.HttpUrl,
        access_token: AccessToken,
    ) -> PullRequest:
        reference: PullRequestReference = (
            create_pull_request_reference_from_url(url=url)
        )

        error_messages: list[str] = []
        if not reference.get("project", None):
            error_messages.append(
                "`project` field missing from "
                + "PullRequestReference decoded from URL.",
            )
        if not reference.get("repository", None):
            error_messages.append(
                "`repository` field missing from "
                + "PullRequestReference decoded from URL.",
            )

        if error_messages:
            url_format_error: ValueError = create_pull_request_url_format_error(
                url=url
            )

            error_message: str = "\n".join(error_messages)

            missing_field_error: ValueError = ValueError(error_message)
            raise url_format_error from missing_field_error

        organisation: OrganisationName = reference.get("organisation")
        project: ProjectName = reference.get("project")  # noqa: invalid-assignment
        repository: GitRepositoryName = reference.get("repository")  # noqa: invalid-assignment
        pull_request_id: PullRequestID = reference.get("pull_request_id")

        connection: azure.devops.connection.Connection = create_connection(
            organisation=organisation,
            access_token=access_token,
        )
        git_client: azure.devops.v7_1.git.git_client.GitClient = (
            connection.clients.get_git_client()
        )
        pull_request: azure.devops.v7_1.git.models.GitPullRequest = (
            git_client.get_pull_request(
                pull_request_id=pull_request_id,
                repository_id=repository,
                project=project,
            )
        )

        return cls(
            api_model=pull_request,
            organisation=organisation,
            project=project,
            repository=repository,
            pull_request_id=pull_request_id,
            access_token=access_token,
        )
