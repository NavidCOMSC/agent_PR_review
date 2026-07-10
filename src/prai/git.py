from __future__ import annotations

from typing import Any
import subprocess
import pathlib

import pydantic
import anyio


class Git:
    def __init__(
        self,
        executable: pydantic.FilePath | str,
    ):
        self.executable = executable

    @classmethod
    async def from_executable(
        cls,
        executable: pathlib.Path | str = "git",
    ) -> Git:
        git_version_output: subprocess.CompletedProcess
        git_version_output = await anyio.run_process(
            f"{executable!s} -v",
        )
        subprocess.CompletedProcess.check_returncode(git_version_output)

        return cls(executable=executable)

    async def exec(
        self,
        command: str,
        *,
        working_directory: pydantic.DirectoryPath | None = None,
    ) -> subprocess.CompletedProcess:
        cwd: pydantic.DirectoryPath
        cwd = pathlib.Path(await anyio.Path.cwd())
        working_directory = working_directory or cwd

        result: subprocess.CompletedProcess
        result = await anyio.run_process(
            f"{self.executable!s} {command}",
            cwd=working_directory,
        )
        return result

    async def clone(
        self,
        url: pydantic.HttpUrl,
        **keyword_arguments: Any,
    ) -> subprocess.CompletedProcess:
        return await self.exec(
            f'clone "{url}"',
            **keyword_arguments,
        )

    async def fetch(
        self,
        remote: str = "origin",
        refspec: str | None = None,
        **keyword_arguments: Any,
    ) -> subprocess.CompletedProcess:
        parts: list[str] = [
            "fetch",
            remote,
        ]
        if refspec:
            parts.append(refspec)

        command: str = " ".join(parts)

        return await self.exec(
            command,
            **keyword_arguments,
        )

    async def checkout(
        self,
        spec: str,
        **keyword_arguments: Any,
    ) -> subprocess.CompletedProcess:
        return await self.exec(
            f"checkout {spec}",
            **keyword_arguments,
        )
