#!/usr/bin/env python3

"""
# # # Usage Option 1: Python API

from trace_utils.find_pipelines import PipelineFinder

finder = PipelineFinder(group_name, project_name)
pipelines = finder.pipelines_by_date(start_datetime, end_datetime)

e.g. pipelines = [
    [22382, '2024-06-01T01:03:08.100Z']
    [22383, '2024-06-01T01:03:08.192Z']
    [22386, '2024-06-01T03:03:05.648Z']
    [22387, '2024-06-01T03:03:06.043Z']
]

# # # Usage Option 2: Parameters on the Command Line from Virtual Environment

Some CI Docker images come with this module pre-installed. The CI user operates
in a shell using a Python virtual environment. The find_pipelines command
is in that virtual environment. A filesystem path is not specified:

find_pipelines -h
usage: find_pipelines [-h] --group GROUP --project PROJECT --start-date START_DATE --end-date END_DATE

Find completed pipelines for a GitLab project that executed between two dates.

optional arguments:
  -h, --help            show this help message and exit
  --group GROUP         The GitLab group where the project resides.
  --project PROJECT     The GitLab project (Git repository) where the pipeline was executed.
  --start-date START_DATE
                        The earliest execution date of a pipeline.
  --end-date END_DATE   The latest execution date of a pipeline.


"""

import argparse
import logging
import sys

from datetime import datetime, timezone
from dateutil.parser import parse

from trace_utils.base_logger import get_logger
from trace_utils.gitlab_common import GitlabProjectBase

log = get_logger(__name__)


def main() -> int:
    args = parse_args()
    if args.debug:
        log.setLevel(logging.DEBUG)

    try:
        gl_project = PipelineFinder(args.group, args.project)
    except RuntimeError as e:
        log.exception(f"Could not create a PipelineFinder object.")
        return 1

    pipeline_ids = gl_project.pipelines_by_date(args.start_date, args.end_date)
    for p in pipeline_ids:
        print(p)

    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        prog="find_pipelines",
        description="Find completed pipelines for a GitLab project that executed between two dates.",
    )
    parser.add_argument("--group", required=True, help="The GitLab group where the project resides.")
    parser.add_argument(
        "--project",
        required=True,
        help="The GitLab project (Git repository) where the pipeline was executed.",
    )
    parser.add_argument("--start-date", required=True, help="The earliest execution date of a pipeline.")
    parser.add_argument("--end-date", help="The latest execution date of a pipeline. Defaults to the current time.")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()
    # Convert string input to Python objects.
    args.start_date = parse(args.start_date)
    if args.end_date:
        args.end_date = parse(args.end_date)
    else:
        args.end_date = datetime.now(timezone.utc)

    return args


class PipelineFinder(GitlabProjectBase):
    """Locates pipelines run in GitLab project by date.

    Once the object is initialized pipelines can be located between two specified dates.
    """

    def __init__(self, group: str, project: str, access_token: str = "") -> list:
        """
        Args:
            group (str): The name of a GitLab group.
            project (str): The name of a GitLab project (GitRepository).
            access_token (str): An access token for GitLab. The token must have "API" privileges.

        Raises:
            RuntimeError: An error occurred during object initialization.
        """
        super().__init__(group, project, access_token)

    def pipelines_by_date(self, start_date: datetime, end_date: datetime):
        """Locate pipelines that were started between two dates.

        Args:
            start_date (datetime): The earliest time that a pipeline was started.
            end_date (datetime): The latest time that a pipeline was started.

        Returns:
            list: A list of tuples is returned in the form (<pipeline ID: int>, <start time: datetime.datetime>).
        """
        pipelines_dates = []
        all_pipelines_found = False

        current_page = 0
        while all_pipelines_found is False:
            current_page += 1
            pipelines = self.project.pipelines.list(page=current_page)
            # The API returns newest Pipelines first. That is, reverse sorted by id, (hence, time).
            for p in pipelines:
                if p.status in ["canceled", "skipped"]:
                    # Ignore pipelines that did not run.
                    continue

                # The GitLab API returns strings not datetime object
                pipeline_date = parse(p.created_at)

                if pipeline_date > end_date:
                    # Ignore early returns which happen after the specified end date. It's backwards...
                    continue
                elif pipeline_date < start_date:
                    # Since the API returns newest first, all remaining pipelines are older than the start date.
                    all_pipelines_found = True
                    break

                # Not earlier. Not later. Goldilocks.
                pipelines_dates.append((p.id, pipeline_date))

                if all_pipelines_found:
                    break

        # Output a more conventional ordering.
        pipelines_dates.reverse()
        return pipelines_dates

    def __str__(self) -> str:
        return ", ".join(
            [
                f"group: ({self.group.id}, {self.group.name})",
                f"project: ({self.project.id}, {self.project.name})",
            ]
        )


if __name__ == "__main__":
    sys.exit(main())
