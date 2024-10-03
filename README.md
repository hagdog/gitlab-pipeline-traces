# gitlab-pipeline-traces

gitlab-pipeline-traces contains excerpts from a repository once used for production CI.
All proprietary code has been removed from this repository. Though, the original filesystem
organization was preserved. Also preserved is work contributed work from Rick Springob.
The work is general in nature and does no impinge upon intellectual property restraints.

The original repository is a shared library for anything related to "CI": continuous integration, container images, compose installations, consolidated instrumentation, etc, etc, etc. It is a collection of scripts, templates, workflows, configurations, and documentation. Each module may be used by different tools.

The retained code shows the implementation of an integration between GitLab and Grafana.
The intent of the integration is provide OTEL compatible traces from GitLab pipelines
in order to provide visualizations of GitLab pipelines not provided by the GitLab GUI itself.

The larger intention of this repository is to demonstrate my understanding and a practical integration of of metrics to assist with visualizations not originally included in
a commercial application. That is, to integrate trace exporting using OTEL with GitLab
pipeline builds.

## Retained Directories

### docker

The docker/ directory contains the Dockerfiles for creating Docker build containers and
various other Docker tasks.

### maintenance

Utilities for maintaining Docker registries in GitLab and AWS ECR.
