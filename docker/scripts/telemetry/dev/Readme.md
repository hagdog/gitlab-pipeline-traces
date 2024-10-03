# Overview

The files in this directory are for use when developing and executing the nearby telemetry code
and testing with environment variables. See the **Development** section for details.

The directory also provides guidance of how to access the telemetry functionality from other GitLab projects.
Additional information is located in the **Integration** section below

# Development

Below are sample commands. The commands are for reference rather than prescribing the order
in which they should be run. Rather, commands are used in consideration of the state of
code in the repository and the state of the virtual Python environment in the shell where the commands are run.

### Package management

Performed at this location:

`~/code/ApplicationRepo/docker/scripts/telemetry`

#### Build the Environment

If you are already running virtual environment:

`deactivate`

Build a new virtual environment based on the desired Python version.

`python3.8 -m venv venv`

`source venv/bin/activate`

`pip install build`

#### Build and Install the Code

`python -m build`

`pip install dist/trace_utils-1.0.0-py3-none-any.whl`

After rebuilding the package first remove then reinstall the package:

`pip install --force-reinstall trace_utils -y`

### Package Usage

#### From the Virtual Environment

Examples:

`find_pipelines --group "robot" --project "ApplicationRepo" --start-date "2024-06-01T22:46:50.251Z" --end-date  "2024-06-12T22:46:50.251Z"`

`export_pipeline_trace cli-args --pipeline 23133 --group "robot" --project "ApplicationRepo" --endpoint console`

When the trace_utils package has been updated:

`deactivate`

`source ~/code/ExportTracesRepo/docker/scripts/telemetry/venv/bin/activate`

#### Command line usage

`deactivate`

`./find_pipelines.py --group "robot" --project "ApplicationRepo" --start-date "2024-06-01T22:46:50.251Z" --end-date  "2024-06-12T22:46:50.251Z"`

`./export_pipeline_trace.py cli-args --pipeline 23133 --group "robot" --project "ApplicationRepo" --endpoint console`

#### Python Interactive

`(venv) $ python`

`>>> from trace_utils.export_pipeline_traces import PipelineExporter`

`>>> from trace_utils.find_pipelines import PipelineFinder`

#### In the tci-docker Image

The trace_utils module is installed into the native Python environment in the image. Therefore the trace_utils content
is avaliable just as with a virtual environment. Follow the usage shown for the virtual environment above.

# Integration

The `task-export-pipeline-trace` task in in the [gitlab-ci.yml](.gitlab-ci.yml) file in this repository performs the export of an OTEL-compatible trace to a GRPC endpoint. The trace contains spans for each job run for a pipeline.

The [post-pipeline.yml](docker/scripts/telemetry/dev/post-pipeline.yml) file in this directory is from
a different repository. The file is located in this repository to demonstrate how the functionality in this
repository is accessed from another repository.

The [post-pipeline.yml](docker/scripts/telemetry/dev/post-pipeline.yml) file runs the `export_pipeline_trace`
job as the last step in a CI pipeline execution. The `export_pipeline_trace` job triggers the remote pipeline run in this repository using the `$EXPORT_PIPELINE_TRACE` variable to trigger a remote pipeline that runs the `task-export-pipeline-trace` job in this repository.
