#!/usr/bin/env python3

"""
This module generates and exports traces of GitLab CI pipelines.

The pipelines are expected to be completed otherwise there would be no end time for the trace.
A new trace ID is generated each time this code is executed. Thefore running the code twice
for the same pipeline ID will generate a duplicate event in the data source since this
exporter does not query the data source for pre-existing traces with matching attributes.

The functionality of this Python module can be used on the command line or by importing
the main class into another Python module or script.


# # # Usage Option 1: Parameters on th the Command Line
Executing this script from the filesystem. (See setup.py for Python required modules.)

Environment: 
  CI: GITLAB_CI_PAT: The GitLab token is set in the environment to keep it hidden.
  Developer: GITLAB_TOKEN: Set your credential in your environment before executing this code.

./export_pipeline_trace.py  cli-args -h
usage: ./export_pipeline_trace.py cli-args [-h] --group GROUP --project PROJECT --pipeline PIPELINE [--endpoint ENDPOINT]

optional arguments:
  -h, --help           show this help message and exit
  --group GROUP        The GitLab group where the project resides.
  --project PROJECT    The GitLab project (Git repository) where the pipeline was executed.
  --pipeline PIPELINE  The completed CI pipeline to produce traces for.
  --endpoint ENDPOINT  The destination for the trace. Can be 'console' or a URL for a GRPC endpoint. The default is the production Grafana instance.

NOTE: Some CI Docker images come with this module pre-installed. The CI user operates
in a shell using a Python virtual environment. The export_pipeline command
is in that virtual environment. A filesystem path is not specified:

export_pipeline_trace cli-args  ...


# # # Usage Option 2: Parameters in the Environment
The command line is executed with no arguments:

usage: ./export_pipeline_trace.py

CI_TRACE_EXPORT_GROUP
CI_TRACE_EXPORT_PROJECT
CI_TRACE_EXPORT_PIPELINE
CI_TRACE_EXPORT_GRPC_ENDPOINT # Optional
CI_TRACE_EXPORT_DEBUG # Optional
GITLAB_CI_PAT | GITLAB_TOKEN

# # # Usage Option 3: Python API

from trace_utils.export_pipeline_traces import PipelineExporter

The simplest example leverages default behaviors:
 a) imports the GitLab token from the environment
 b) uses the default trace destination of the production instance of Grafana.
    pipeline_exporter = PipelineExporter("robot", "ApplicationRepo", 23221)

Extra key/value pairs are propagated to all spans.
    pipeline_exporter.generate_trace(exra_arg1="foo", extra_arg2="bar")

Using the otel-demo stack in tools/ExportTracesRepo to test locally:
    pipeline_exporter.generate_trace(endpoint="http://localhost:4518")
"""
import argparse
import logging
import os
import sys

import gitlab
from dateutil.parser import parse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from trace_utils.base_logger import get_logger
from trace_utils.gitlab_common import GitlabProjectBase, get_gitlab_token

DEFAULT_GRPC_ENDPOINT = "http://redacted:4518"


log = get_logger(__name__)


def main() -> int:
    """Entry point when executing via command line."""
    try:
        gitlab_token = get_gitlab_token()
    except RuntimeError as e:
        log.exception(f"Cannot generate a trace from GitLab.")
        return 1

    args = parse_args()
    if args.debug:
        log.setLevel(logging.DEBUG)

    try:
        log.info(f"Sending trace {args.group}:{args.project}:{args.pipeline} to {args.endpoint}.")
        trace_exporter = PipelineExporter(args.group, args.project, gitlab_token)
        trace_exporter.generate_trace(args.pipeline, args.endpoint)
        log.info(f"Trace successfully exported for pipeline #{args.pipeline}")
        return 0
    except Exception:
        log.exception(f"Export of pipeline trace failed.")
        return 1


def parse_args() -> any:
    """Manage command line arguments.

    When this module is run as a script parameters can be provided to the script
    in two different ways. Parameters can be supplied on a command line or parameters
    can be specified via environment variables. Command line parameters override environment varibles.
    """

    # Command line arguments override
    args = _parse_args_cli()
    if not _have_args(args):
        print("No commmand line arguments detected. Checking the environment")
        args = _parse_args_env()

    return args


def _have_args(args) -> bool:
    """If an argument parser has been run and set values for parameters or options."""
    if getattr(args, "pipeline", None):
        # Only one parameter needs checking since all args are required.
        return True
    return False


def _parse_args_cli():
    parser = argparse.ArgumentParser(
        prog=sys.argv[0],
        description="Generates and exports traces for a pipeline.",
        epilog="Contact DevOps before sending traces to DevOps-managed Grafana instances.",
    )
    # A subparser gives us a two-mode command line. One mode retrieves parameters from the command line
    # while the other mode retrieves parametes from the environment. The latter mode is generally used in CI pipelines.
    #
    # When the subparser is specified, argparse handles required args and default values for command line parameters.
    # No arguments are accepted when the subparser in not specified. The environment must supply parameters.
    # The same usage logic is used in bothe parser modes.
    subparsers = parser.add_subparsers()
    cli_parser = subparsers.add_parser("cli-args")

    cli_parser.add_argument("--group", help="The GitLab group where the project resides.")
    cli_parser.add_argument(
        "--project",
        help="The GitLab project (Git repository) where the pipeline was executed.",
    )
    cli_parser.add_argument("--pipeline", type=int, help="The completed CI pipeline to produce traces for.")
    cli_parser.add_argument(
        "--endpoint",
        default=DEFAULT_GRPC_ENDPOINT,
        help="The destination for the trace. Can be 'console' or a GRPC endpoint. "
        "Default is the production Grafana instance.",
    )
    cli_parser.add_argument("--debug", action="store_true", default=False)

    args = parser.parse_args()
    log.debug(f"args in _parse_args_cli(): {args}")
    try:
        if not args.endpoint.startswith("http") and args.endpoint != "console":
            cli_parser.error("The endpoint must be a valid network address or 'console'.")
    except AttributeError:
        # Not an error.
        # The subparser was not used so there are no command line parameters.
        # An empty Namespace object is returned.
        pass

    return args


def _parse_args_env():
    required_params = [
        "group",
        "project",
        "pipeline",
    ]
    supported_params = {
        "group": "CI_TRACE_EXPORT_GROUP",
        "project": "CI_TRACE_EXPORT_PROJECT",
        "pipeline": "CI_TRACE_EXPORT_PIPELINE",
        "endpoint": "CI_TRACE_EXPORT_GRPC_ENDPOINT",
        "debug": "CI_TRACE_EXPORT_DEBUG",
    }
    # A simplistic parser provides a namespace and helps manage errors.
    parser = argparse.ArgumentParser(usage="")
    args = parser.parse_args()

    # Get values from the environment
    for key in supported_params.keys():
        setattr(args, key, os.environ.get(supported_params[key]))

    # Verify required values
    missing_values = []
    for key in required_params:
        if getattr(args, key) is None:
            missing_values.append(supported_params[key])
    if missing_values:
        parser.error(f"The following variables must be defined in the environment: {missing_values}")

    # Optional value
    if not args.endpoint:
        args.endpoint = DEFAULT_GRPC_ENDPOINT

    log.debug(f"args in _parse_args_env(): {args}")
    return args


class ObjectDictNormalizer:
    @staticmethod
    def map_attributes(flat_map: dict, nested_map: dict, gitlab_obj) -> dict:
        """Map attributes of a GitLab object to otel-compatible attributes dictionary.

        Args:
            flat_map: A list of mappings for attributes in the form:
                        [<trace label>, <GitLab attribute>, <default value>]
            nested_map: A list of mappings for a two-level nested dictionary in the form:
                          [<trace label>, <GitLab attribute>, <GitLab nested attribute>, <default value>]
            gitlab_obj: A GitLab object such as a job or pipeline.

        Returns:
            A dictionary of name/value pairs. The values are Python primative types of lists of primatives
                compatible with otel trace attributes, e.g. no dictionaries or class instances.
        """
        data_in = gitlab_obj.asdict()
        data_out = {}

        for item in flat_map:
            dest_name, src_name, default_value = item
            try:
                if data_in[src_name] is None:
                    # GitLab can use differnt data types, e.g. None instead of an empty dictionary.
                    data_out[dest_name] = int(default_value) if isinstance(default_value, int) else default_value
                else:
                    data_out[dest_name] = data_in[src_name]
            except KeyError:
                # Missing value. But, put the key in the attribute list.
                data_out[dest_name] = int(default_value) if isinstance(default_value, int) else default_value

        for item in nested_map:
            dest_name, src_name, nested_name, default_value = item
            try:
                if data_in[src_name] is default_value:
                    # A dictionary with a second level of keys is expected,
                    data_out[dest_name] = None
                else:
                    if isinstance(data_in[src_name], dict):
                        data_out[dest_name] = data_in[src_name][nested_name]
                        if data_out[dest_name] is None:
                            data_out[dest_name] = (
                                int(default_value) if isinstance(default_value, int) else default_value
                            )
                    else:
                        data_out[dest_name] = int(default_value) if isinstance(default_value, int) else default_value
            except KeyError:
                # Missing value. But, put the key in the attribute list.
                data_out[dest_name] = int(default_value) if isinstance(default_value, int) else default_value

        return data_out

    @staticmethod
    def map_spans(gitlab_obj, pipeline_started_at):
        # GitLab is inconsistent with the values of start and end times for jobs.
        # At times one or both times are None or "". This method standardizes the values to normalize span times.
        #
        # When the both times are defined, the times are converted to nanoseconds since the epoch.
        # When a time is None, the defined time is used for the other time. That is, start to end, or end to start.
        # When no times are defined, the pipeline start date is applied to both stop and end.
        # In summary, all job spans containing undefined time values will have a duration of 0.
        object_type = ObjectDictNormalizer.get_object_type_str(gitlab_obj)
        if not gitlab_obj.started_at and not gitlab_obj.finished_at:
            log.info(
                "Appyling pipeline start time to missing "
                f"started_at and finished_at times for {object_type} #{gitlab_obj.id}."
            )
            gitlab_obj.started_at = pipeline_started_at
            gitlab_obj.finished_at = pipeline_started_at
        elif not gitlab_obj.started_at and gitlab_obj.finished_at:
            log.info(f"Applying finished_at time for missing started_at time for {object_type} #{gitlab_obj.id}.")
            gitlab_obj.started_at = gitlab_obj.finished_at
        elif not gitlab_obj.finished_at and gitlab_obj.started_at:
            # This has not been seen. Try to prevent an outlying data point in case it happens.
            log.info(f"Applying started_at time for missing finished_at time for {object_type} #{gitlab_obj.id}.")
            gitlab_obj.finished_at = gitlab_obj.started_at

        return (
            # The GitLab API time values are strings, e.g. '2024-07-10T20:51:33.581Z'
            int(parse(gitlab_obj.started_at).strftime("%s")) * 10 ** 9,
            int(parse(gitlab_obj.finished_at).strftime("%s")) * 10 ** 9,
        )

    @staticmethod
    def get_object_type_str(gitlab_obj) -> str:
        raw_type_str = str(type(gitlab_obj))
        if "ProjectPipelineJob" in raw_type_str:
            return "job"
        elif "ProjectPipeline" in raw_type_str:
            return "pipeline"
        else:
            return raw_type_str


class JobTraceData(ObjectDictNormalizer):
    """Attributes used by job spans."""

    # Each map item: [<trace label>, <GitLab API attribute>, <default value>]
    flat_map = [
        ["name", "name", ""],
        ["finished_at", "finished_at", ""],
        ["job_id", "id", ""],
        ["queued_duration", "queued_duration", 0],
        ["ref", "ref", ""],
        ["stage", "stage", ""],
        ["started_at", "started_at", ""],
        ["status", "status", ""],
        ["web_url", "web_url", ""],
    ]
    # Each map item: [<trace label>, <GitLab API attribute>, <GitLab nested attribute>, <default value>]
    two_level_map = [
        ["commit", "commit", "id", ""],
        ["runner_id", "runner", "id", 0],
        ["runner_name", "runner", "name", ""],
        ["runner_description", "runner", "description", ""],
    ]

    def __init__(self, gitlab_job, pipeline_started_at, **extra_attrs) -> None:
        """
        Args:
            gitlab_job : A job object retrieved by the GitLab API
            pipeline_started_at: A GitLab API style time string of when the pipeline started.
            **extra_attrs: Key/value pairs to be added to the attributes of a span.
        """
        self.span_start, self.span_end = ObjectDictNormalizer.map_spans(gitlab_job, pipeline_started_at)
        self.attributes = ObjectDictNormalizer.map_attributes(self.flat_map, self.two_level_map, gitlab_job)

        if extra_attrs:
            self.attributes.update(extra_attrs)

        log.debug(
            f"Job attributes generated: {self.attributes}, Times: span_start = {self.span_start}, span_end = {self.span_end}"
        )


class PipelineTraceData(ObjectDictNormalizer):
    """Attributes used by the parent (pipeline) span."""

    # Each map item: [<trace label>, <GitLab attribute>, <default value>]
    flat_map = [
        ["id", "id", 0],
        ["project_id", "project_id", 0],
        ["queued_duration", "queued_duration", 0],
        ["ref", "ref", ""],
        ["source", "source", ""],
        ["status", "status", ""],
        ["web_url", "web_url", ""],
    ]
    # Each map item: [<trace label>, <GitLab attribute>, <GitLab nested attribute>, <default value>]
    two_level_map = [
        ["user", "user", "name", ""],
        ["username", "user", "username", ""],
    ]

    def __init__(self, gitlab_pipeline, project_name: str, **extra_attrs) -> None:
        """
        Args:
            gitlab_pipeline : A pipeline object retrieved by the GitLab API
            project_name : The name of the project (Git repository) the pipeline ran in.
            **extra_attrs: Key/value pairs to be added to the attributes of a span.
        """
        self.attributes = ObjectDictNormalizer.map_attributes(self.flat_map, self.two_level_map, gitlab_pipeline)
        self.attributes["project_name"] = project_name
        self.span_start, self.span_end = ObjectDictNormalizer.map_spans(gitlab_pipeline, gitlab_pipeline.started_at)

        log.debug(
            f"Pipeline attributes generated: {self.attributes}, Times: span_start = {self.span_start}, span_end = {self.span_end}"
        )


class TraceResourceData:
    """Resource attributes used by all spans in a trace.

    The attributes can be directly applied as resource attributes
    during the intialization of a Resource object from the opentelemetry API.
    """

    def __init__(self, group, project, pipeline, **extra_attrs) -> None:
        """
        Args:
            group (Group): A group object retrieved by the GitLab API.
            project (Project): A project object (Git repository) retrieved by the GitLab API
            pipeline (ProjectPipeline): A pipeline object retrieved by the GitLab APIGitLabBase
            **extra_attrs (dict): Key/value pairs to be added to the attributes of a span.
        """
        self.attributes = {
            "pipeline_id": pipeline.id,
            "pipeline_source": pipeline.source,
            "piipeline_status": pipeline.status,
            "pipeline_url": pipeline.web_url,
            "gitlab_group": group.name,
            "gitlab_project": project.name,
            "service.name": f"{project.name}-pipeline",
            "user": pipeline.user.get("name", "none"),
            "username": pipeline.user.get("username", "none"),
        }
        if extra_attrs:
            self.attributes.update(extra_attrs)
        log.debug(f"Resource attributes generated: {self.attributes}")


class PipelineExporter(GitlabProjectBase):
    """Produces a trace for a pipeline execution ran in GitLab.

    The PipelineExporter retrieves pipeline information from GitLab including
    jobs run during pipeline execution. The start and finish times are handled
    differently from most traces. Traces are generally created automatically
    and therefore use start and finish times as they occur.
    In contrast, the PipelineExporter applies the start and finish time from
    for the pipeline and its associated jobs. The PipelineExporter also applies
    attributes to the span and in the resource context.

    The PipelineExporter sends traces to either the console or a GRPC endpoint.
    The destination is provided by the user of this class.

    Usage:
    import PipelineExporter

    trace_exporter = PipelineExporter(group, project, gitlab_token="")
    trace_exporter.generate_trace(pipeline, endpoint=DEFAULT_GRPC_ENDPOINT)
    """

    def __init__(
        self,
        group: str,
        project: str,
        access_token: str = "",
    ) -> None:
        """
        Args:
            group (str): The name of a GitLab group.
            project (str): The name of a GitLab project (GitRepository).
            access_token (str): An access token for GitLab. The token must have "API" privileges.

        Raises:
            RuntimeError: An error occurred during object initialization.
        """
        super().__init__(group, project, access_token)
        self.pipeline = 0
        self._have_trace_provider = False
        log.debug(f"PipelineExporter initialized: {self}")

    def generate_trace(self, pipeline_id: int, endpoint: str = DEFAULT_GRPC_ENDPOINT, **extra_attrs):
        """Builds a trace from a CI pipeline in GitLab. The parent span represents the pipeline
        itself. A child span is created for each job ran during pipeline execution.

        Args:
            endpoint (str, optional): Where the trace will be sent to. If the endpoint is
              not provided the trace will go to the default endpoint. If the endpoint is
              an empty string, the trace is sent to the console--usually only used during
              script development.
            **extra_attrs (dict): Key/value pairs to be added to the attributes and resources of all spans.

        Raises:
            RuntimeError: The exception is raised if an operation fails in the preparation or
            delivery of the trace. Context in provided in the exception string.
        """
        self.pipeline = self._retrieve_pipeline(pipeline_id)
        log.info(
            f"Sending trace: project='{self.project.name}', ref='{self.pipeline.ref}', pipeline={self.pipeline.id} to {endpoint}."
        )
        log.debug(f"Retrieved pipeline from GitLab: {self.pipeline.asdict()}")

        if self.pipeline.source == "schedule":
            schedule = self._find_pipeline_schedule(pipeline_id)

            if schedule:
                log.info(f"Schedule found for pipeline {pipeline_id}: {schedule}")
                extra_attrs["schedule_id"] = schedule.id
                # There is no 'name' attribute on GitLab schedule objects so 'description' is used.
                extra_attrs["schedule_description"] = schedule.description
                log.debug(f"Schedule information added to spans.")
            else:
                log.warning(f"Schedule not found for pipeline {pipeline_id}. The schedule may have been deleted.")

        pipeline_resources = TraceResourceData(self.group, self.project, self.pipeline, **extra_attrs)
        if endpoint == "console":
            tracer = self._get_console_tracer(pipeline_resources)
        else:
            tracer = self._get_grpc_tracer(pipeline_resources, endpoint)

        # The pipeline provides context that will be inherited by its jobs.
        pipeline_span_data = PipelineTraceData(self.pipeline, self.project.name, **extra_attrs)
        with tracer.start_as_current_span(
            f"pipeline-{self.pipeline.id}",
            start_time=pipeline_span_data.span_start,
            attributes=pipeline_span_data.attributes,
            end_on_exit=False,
        ):
            pipeline_span = trace.get_current_span()
            pipeline_span.set_attribute("started_at_nano", pipeline_span_data.span_start)
            pipeline_span.set_attribute("finished_at_nano", pipeline_span_data.span_end)
            log.debug(
                f"pipeline_span: span time = {{span_start: {pipeline_span_data.span_start}, "
                f"span_end: {pipeline_span_data.span_end}}}\n span data = {pipeline_span.to_json()}"
            )

            jobs = self.pipeline.jobs.list()
            for job in jobs:
                job_span_data = JobTraceData(job, self.pipeline.started_at)
                with tracer.start_as_current_span(
                    job.name,
                    start_time=job_span_data.span_start,
                    attributes=job_span_data.attributes,
                    end_on_exit=False,
                ):
                    job_span = trace.get_current_span()
                    job_span.end(job_span_data.span_end)
                    log.debug(
                        f"job span: span time = {{span_start: {job_span_data.span_start}, "
                        f"span_end: {job_span_data.span_end}}}\n span data = {job_span.to_json()}"
                    )
            pipeline_span.end(pipeline_span_data.span_end)
            log.info(
                f"Sent trace: project='{self.project.name}', ref='{self.pipeline.ref}', pipeline={self.pipeline.id} to {endpoint}."
            )

    def _find_pipeline_schedule(self, pipeline_id: int) -> any:
        """Locate the schedule used to launch a CI pipeline.

        Warning: GitLab schedules only have descriptions, not names. And, the description
        can be modified at any point of its existence. As a result the schedule description
        recorded in a older trace attributes may differ from the current description. The schedule
        ID does not change. Both the ID and description are included in spans so that either
        value can be used when querying for pipelines launched by a schedule.

        Args:
            pipeline_id (int): The pipeline ID.

        Raises:
            RuntimeError: The exception is raised if an operation fails
            while looking up schedules.

        Returns:
            A GitLab schedule object is returned when a match is found. Otherwise, None.
        """
        try:
            schedules = self.project.pipelineschedules.list(get_all=True)
        except gitlab.exceptions.GitlabError as e:
            raise RuntimeError(f"Cannot retrieve schedules: {e.error_message}")

        # The GitLab API does not include schedules in pipeline objects nor useful lookup functionality.
        # The recourse is to use a brute force search. Get all schedules for a gitlab project and
        # locate the pipeline ID in a schedule instance.
        sched_for_pipeline = None
        for schedule in schedules:
            log.debug(f"Processing schedule: {schedule}")
            sched_pipelines = schedule.pipelines.list(get_all=True, iterator=True)
            sched_pipeline_ids = [p.id for p in sched_pipelines]
            log.debug(f"Pipelines for schedule: {sched_pipeline_ids}")

            if pipeline_id in sched_pipeline_ids:
                sched_for_pipeline = schedule
                break

        if sched_for_pipeline:
            return sched_for_pipeline
        else:
            return None

    def _get_console_tracer(self, pipeline_resources: PipelineTraceData) -> any:
        """Initialize an OpenTelemetry Tracer object that sends a trace to the console.

        Data from the the pipeline is applied to attributes in the Resource of the
        TracerProvider. The resource attributes are propagated to all spans.

        Args:
            pipeline_resources (_type_): Important key/value pairs including from
            the relevant group, project, and pipeline.

        Returns:
            A Tracer object from the OpenTelemetry API
        """
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        resource = Resource(attributes=pipeline_resources.attributes)
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(processor)
        if not self._have_trace_provider:
            # The Provider is set once. Avoid logged warnings by not violating the otel module's paradigm.
            trace.set_tracer_provider(provider)
            self._have_trace_provider = True

        return trace.get_tracer(__name__)

    def _get_grpc_tracer(self, pipeline_resources, endpoint):
        """Initialize an OpenTelemetry Tracer object compatible with a GRPC endpoint.

        Data from the the pipeline is applied to attributes in the Resource of the
        TracerProvider. The resource attributes are propagated to all spans.

        Args:
            pipeline_resources (_type_): Important key/value pairs including from
            the relevant group, project, and pipeline.

        Returns:
            A Tracer object from the OpenTelemetry API
        """
        if not self._have_trace_provider:
            # The Provider is set once. Avoid logged warnings by not violating the otel module's paradigm.
            resource = Resource(attributes=pipeline_resources.attributes)
            trace.set_tracer_provider(TracerProvider(resource=resource))
            self._have_trace_provider = True

        otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
        span_processor = BatchSpanProcessor(otlp_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)

        return trace.get_tracer(__name__)

    def _retrieve_pipeline(self, pipeline_id: int):
        """Retrieve the GitLab pipeline object for the given group name.

        Args:
            pipeline_id (int): The ID for the pipeline object sought.

        Raises:
            RuntimeError: The exception is raised if an operation fails
            while looking up or retrieving pipelines.

        Returns:
            The GitLab ProjectPipeline object for the requested pipeline.
        """
        log.info(f"Retrieving pipeline #{pipeline_id}.")
        try:
            pipeline = self.project.pipelines.get(pipeline_id)
            log.debug(f"Pipeline retrieved: {pipeline}.")
        except gitlab.exceptions.GitlabError as e:
            raise RuntimeError(f"Could not retrieve pipeline {pipeline_id}: {e.error_message}") from e

        return pipeline

    def __str__(self) -> str:
        attrs = [
            f"group: ({self.group.id}, {self.group.name})",
            f"project: ({self.project.id}, {self.project.name})",
        ]
        try:
            p_str = f"pipeline: ({self.pipeline.id}, {self.pipeline.name})"
        except AttributeError:
            # Uninitialized
            p_str = f"pipeline: ({self.pipeline}, {self.pipeline})"

        attrs.append(p_str)
        return ", ".join(attrs)


if __name__ == "__main__":
    sys.exit(main())
