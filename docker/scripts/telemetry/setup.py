from setuptools import find_packages, setup

setup(
    name="trace_utils",
    version="1.0.1",
    description="Exports a trace of a GitLab pipeline to Grafana",
    author="Rick Springob",
    author_email="rspringob@gmail.com",
    url="https:redacted",
    packages=find_packages(where="src"),
    install_requires=[
        # Should be no version-specific needs on these stable modules.
        "opentelemetry-api",
        "opentelemetry-exporter-otlp-proto-grpc",
        "opentelemetry-sdk",
        "python-dateutil",
        "python-gitlab",
    ],
    package_dir={"trace_utils": "src/trace_utils"},
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "export_pipeline_trace = trace_utils.export_pipeline_trace:main",
            "find_pipelines = trace_utils.find_pipelines:main",
        ]
    },
)
