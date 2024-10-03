"""
Functions and global constants commonly imported by modules in this package.
"""

import logging
import os
import re
from pathlib import Path

import gitlab

from trace_utils.base_logger import get_logger

GITLAB_URL = "https://redacted"
PAGINATION_COUNT = 200


log = get_logger(__name__)


def get_gitlab_token() -> str:
    """Retrieves a user's GitLab token.

    Various attempts are made to locate the user's GitLab credentials.
    Locations include credential files in a user's home directory
    and the GITLAB_TOKEN and a GitLab CI environment variable.

    Returns:
        str: A GitLab token.
    """
    token = token_from_env()
    if not token:
        token = token_from_tokenfile()
    if not token:
        token = token_from_credential_file()
    if not token:
        raise RuntimeError("Could not locate a GitLab token. See debug logs for details.")

    return token


def token_from_credential_file(token_path="") -> str:
    """Extracts a GitLab token from a credentials file containing
    a URL to GitLab that includes the user's credentials.

    The user token must have privileges to use the GitLab API.

    If token_path is not supplied, ~/.gitlab-credentials will be checked.

    Args:
        token_path (str, optional): The full path to a credentials file. Defaults to "".

    Returns:
        str: The GitLab token.
    """
    token = ""
    if not token_path:
        token_path = Path(os.environ.get("HOME", "")) / ".gitlab-credentials"

    try:
        # The GitLab credential file contains a single line containing a URL to GitLab with an embedded token.

        with open(token_path) as f:
            gitlab_url = f.readline()
        log.info(f"Retrieved GitLab token from {token_path}.")
    except (IOError, OSError) as e:
        log.debug(f"GitLab token not found at {token_path}: {e}")
        return ""

    # e.g. https://user.name:token@gitlab.mydomain.com
    m = re.search(r"^.+:\S+:(.+)@.*$", gitlab_url)
    if m:
        token = m.group(1)

    return token


def token_from_env(var_name: str = "") -> str:
    """Reads the GitLab token from an environment variable

    The user token must have privileges to use the GitLab API.

    If var_name is not supplied, GITLAB_TOKEN will be checked.
    When using with GitLab CI and internal value is inspected.

    Args:
        var_name (str, optional): The environment variable name. Defaults to "".

    Returns:
        str: The GitLab token.
    """

    if var_name:
        # Fail if the imperative is not defined.
        return os.environ.get(var_name, "")

    token = os.environ.get("GITLAB_TOKEN")
    if token:
        log.info("Retrieved GitLab token from the environment variable GITLAB_TOKEN.")
        return token

    token = os.environ.get("GITLAB_CI_PAT")
    if token:
        log.info("Retrieved GitLab token from GitLab CI environment.")
        return token

    return ""


def token_from_tokenfile(token_path: str = "") -> str:
    """Reads the GitLab token from a file containing the GitLab token.

    The user token must have privileges to use the GitLab API.

    If token_path is not supplied, ~/.tokens/gitlab will be checked.

    Args:
        token_path (str, optional): The full path to a credentials file. Defaults to "".

    Returns:
        str: The GitLab token.
    """
    token = ""
    if not token_path:
        token_path = Path(os.environ.get("HOME", "")) / ".tokens/gitlab"

    try:
        # The GitLab token file should have a single line containing the token.
        with open(token_path) as f:
            token = f.readline()
        log.info(f"Retrieved GitLab token from {token_path}.")
    except (IOError, OSError) as e:
        log.debug(f"GitLab token not found at {token_path}: {e}")
        return ""

    return token.strip()


class GitlabProjectBase:
    """The GitlabProjectBase is essentially a wrapper for group and project objects
    from the GitLab API.

    This class is not meant to enhance the GitLab API functionality. Rather, this
    class is designed as a base class to be leveraged by classes that supply
    functionality to other GitLab constructs such as pipelines and schedules.
    """

    def __init__(self, group: str, project: str, access_token: str = "") -> None:
        """
        Args:
            group (str): The name of a GitLab group.
            project (str): The name of a GitLab project (GitRepository).
            access_token (str): An access token for GitLab. The token must have "API" privileges.
        """
        if not access_token:
            access_token = get_gitlab_token()

        self.gl_client = gitlab.Gitlab(
            url=GITLAB_URL,
            private_token=access_token,
            pagination="keyset",
            order_by="id",
            per_page=PAGINATION_COUNT,
        )
        self.group = self._retrieve_group(group)
        self.project = self._retrieve_project(project)

    def _retrieve_group(self, group_name: str) -> any:
        """Retrieve the GitLab group object for the given group name.

        Args:
            group_name (str): The name of the group that owns the project of the pipeline.

        Raises:
            RuntimeError: The exception is raised if an operation fails
            while looking up or retrieving schedules.

        Returns:
            A GitLab group object
        """
        try:
            groups = self.gl_client.groups.list(get_all=True, iterator=True, lazy=True)
        except gitlab.exceptions.GitlabError as e:
            raise RuntimeError(f"Cannot retrieve groups: {e.error_message}")

        for group in groups:
            if group_name == group.name:
                # Full objects come from 'get' rather than 'list' operations.
                return self.gl_client.groups.get(group.id)

        raise RuntimeError(f"Group '{group_name}' not found or does not exist.")

    def _retrieve_project(self, project_name: str) -> int:
        """Retrieve a GitLab project.

        Args:
            project_name (str): The full name of the GitLab project.

        Raises:
            RuntimeError: The exception is raised if an operation fails
            while looking up or retrieving projects.

        Returns:
            The GitLab Project object specified project by the project name.
        """
        try:
            projects = self.group.projects.list(get_all=True, iterator=True, lazy=True)
        except gitlab.exceptions.GitlabError as e:
            raise RuntimeError(f"Cannot retrieve project: {e.error_message}")

        for project in projects:
            if project.name == project_name:
                # Full objects come from 'get' rather than 'list' operations.
                return self.gl_client.projects.get(project.id)

        raise RuntimeError(f"Project '{project_name}' not found or does not exist in group '{self.group.name}'.")
