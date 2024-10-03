#!/usr/bin/env python3

"""
This script is used to populate a test instance of Grafana with pipeline test data.
The data can be used to help develop visualizations in Grafana.

This script should only be executed by DevOps using the GRPC endpoint
for the production instance of Grafana.

Important: If you  run this script multiple times with using the same
group, project, and time setting, the data will be duplicated in Grafana.
While not harmful, per se, visualizations will be inaccurate.

Though this script is only meant to be exeucted in rare circumstances
using production endpoints, the script has been left here
as an illustration the usage of trace_utils classes.
"""

import sys

from dateutil.parser import parse

from trace_utils.base_logger import get_logger
from trace_utils.find_pipelines import PipelineFinder
from trace_utils.export_pipeline_trace import PipelineExporter

# Export trace data to the terminal where the script is run.
DEFAULT_GRPC_ENDPOINT = "console"
# A developer running the otel-demo stack locally.
# DEFAULT_GRPC_ENDPOINT = "http://localhost:4518"
GITLAB_URL = "https://gitlab.mydomain.com"

log = get_logger(__name__)


def main() -> int:
    finder = PipelineFinder("robot", "ApplicationRepo")
    exporter = PipelineExporter("robot", "ApplicationRepo")

    start_date = parse("2024-06-03T00:00:00.000Z")
    end_date = parse("2024-06-04T23:59:59.999Z")
    pipelines = finder.pipelines_by_date(start_date, end_date)
    # pipelines => [[22382, '2024-06-01T01:03:08.100Z'], [22383, '2024-06-01T01:03:08.192Z'], ...]

    for p in pipelines:
        log.info(f"Exporting pipeline: {p}")
        exporter.generate_trace(pipeline_id=p[0], endpoint=DEFAULT_GRPC_ENDPOINT)

    return 0


if __name__ == "__main__":
    sys.exit(main())
