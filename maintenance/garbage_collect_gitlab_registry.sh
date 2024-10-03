#!/bin/bash

# Support the DRY_RUN environment variable which is in common use in this CI framework.
case $DRY_RUN in
  "1" | "t" | "true"| "y" | "yes")
    do_work="false"
    ;;
  *)
    do_work="true"
    ;;
esac

if [[ "$do_work" == "true" ]]; then
    echo "Garbage collection starting for the GitLab Docker registrry."
    docker exec -i redacted-registry registry garbage-collect -m /etc/docker/registry/config.yml
else
    echo "DRY_RUN is indicated in the environment: DRY_RUN=${DRY_RUN}. "
    echo "Garbage collection will not be performed in the GitLab Docker registry."
fi
