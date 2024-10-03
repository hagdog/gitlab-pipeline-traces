This folder contains Dockerfiles and scripts used to build CI-related Docker images. These images, in the repositories `tci-*`, are tagged using the [version.txt](../version.txt) at the root of the repository and are used as the source images for ExportTracesRepo builds.

Diagrams in [docker-images-build-flow.drawio](../docs/diagrams/docker/docker-images-build-flow.drawio):

- Shows the relationships between the files used in building Docker images.
- Shows how to select images to build. You can also use the variables shown in the GitLab GUI.

See [../docs/diagrams/README.md](../docs/diagrams/README.md) if you need help with rendering image files in VSCode.
