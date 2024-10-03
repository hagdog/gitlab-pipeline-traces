#!/usr/bin/env python3
"""

Environment Variables:
  Environment variables are used to facilitate CI pipelines rather than command line parameters.

  Imported:
    DRY_RUN: With the value of "true", deletion candidates are identified but not deleted from ECR.
             If undefined or "false", images are deleteed.

  Required in the Environment but not Imported:
    PG_USER: The user to query the database for releases deployed to robots in the field.
    PGPASSWORD: The password for PG_USER
    RDSHOST: The database server name.

"""

import boto3
import os
import pytz
import re
import sys
from datetime import datetime, timedelta, timezone

from psycopg2 import OperationalError

from redacted_common_py import constants
from dataapi.robots.oee import get_oee_config_permutations

MFR = "redacted/main-full-runtime"
REPO_PREFIXES = [
    "redacted/main",
    "redacted/arm",
    "redacted/hwif",
    "redacted/fiddle",
    "redacted/gong",
]
TAG_KEEP_PATTERNS = [
    re.compile(r"^.*latest$"),
    re.compile(r"^dev_nightly$"),
    re.compile(r"^rel-\d{4}\.\d{2}\.\d{2}(?:_\d+)?$"),
    re.compile(r"^rel-\d{4}\.\d{2}\.\d{2}_nightly$"),
]
KEEP_DAYS = 90
LOCAL_TZ = "America/Denver"


def main() -> int:
    errs = 0

    dry_run = os.getenv("DRY_RUN", "False").lower() in ("1", "t", "true", "y", "yes")

    client = boto3.client("ecr")
    repository_names = all_repo_names(client)
    try:
        all_field_versions = get_deployed_containers()
    except RuntimeError as e:
        print(f"Database query failed: {e}")
        errs += 1

    if not errs:
        print("Analyzing deletion candidates. This can take awhile.")
        categorized_images = categorize_images(client, repository_names, all_field_versions)
        deletion_data = delete_images(client, categorized_images, dry_run)

        report_skipped(categorized_images, all_field_versions)
        report_deleted(deletion_data["deletion_report"])
        if dry_run:
            print(
                f"{deletion_data['num_images']} images, "
                f"({gb_str_from_bytes(deletion_data['num_bytes'])} GB) would be deleted."
            )
        else:
            print(
                f"{deletion_data['num_images']} images deleted and "
                f"({gb_str_from_bytes(deletion_data['num_bytes'])} GB) were reclaimed."
            )

    return 0


def all_repo_names(client) -> list:
    repositories = []
    paginator = client.get_paginator("describe_repositories")
    for page in paginator.paginate():
        for repo in page["repositories"]:
            if any([repo["repositoryName"].startswith(prefix) for prefix in REPO_PREFIXES]):
                repositories.append(repo["repositoryName"])
    return repositories


def batch(iterable, n=1):
    """Yield successive n-sized chunks from iterable."""
    length = len(iterable)
    for i in range(0, length, n):
        yield iterable[i : min(i + n, length)]


def categorize_images(client, repository_names: list, all_field_versions: list):
    categorized_images = {}
    for repo in repository_names:
        repo_categorized_images = categorize_images_by_repo(client, repo, all_field_versions)
        if repo_categorized_images:
            categorized_images[repo] = repo_categorized_images

    return categorized_images


def categorize_images_by_repo(client, repository_name: str, all_field_versions: dict) -> dict:
    images = {"recent": [], "fielded": [], "keep_pattern": [], "deletable": []}

    # Paginate through list of images in the repository
    image_paginator = client.get_paginator("list_images")
    for image_page in image_paginator.paginate(
        registryId=constants.RESOURCES.AWS_ACCT_ID, repositoryName=repository_name
    ):
        for image in image_page["imageIds"]:
            image_size = 0

            # Paginate through image details to find out when it was pushed
            detail_paginator = client.get_paginator("describe_images")
            for detail_page in detail_paginator.paginate(
                repositoryName=repository_name, imageIds=[image]
            ):
                retain = False
                for image_details in detail_page["imageDetails"]:
                    image_size = image_details.get("imageSizeInBytes", 0)
                    image_tags = image_details.get("imageTags", [])

                    if image_tags:
                        for tag in image_tags:
                            if matches_keep_pattern(tag):
                                images["keep_pattern"].append(tag)
                                retain = True
                                break
                    else:
                        # No tags in the image details.
                        tag = image.get("imageTag", "")

                    if not retain and tag and is_fielded(tag, repository_name, all_field_versions):
                        images["fielded"].append(tag)
                        retain = True

                    if not retain and is_recent(image_details["imagePushedAt"]):
                        # imagePushedAt is local, "datetime(...., tzinfo=tzlocal())"
                        images["recent"].append(tag)
                        retain = True

                    if retain:
                        # A reason was found to retain this image. No need to reclassify it.
                        break
                if retain:
                    break

            if not retain:
                # Every reason to retain this image has been eliminated.
                # deletable example: ({"imageDigest": "sha256:e92e8...", "imageTag": "rel-2022.09.16"}, 9935662402)
                images["deletable"].append((image, image_size))

    return images


def delete_images(client, categorized_images: dict, dry_run: bool):
    total_bytes_deleted = 0
    total_images_deleted = 0
    deletion_report = []
    for repo_name, repo_images in categorized_images.items():
        repo_candidates = repo_images.get("deletable")
        if not repo_candidates:
            print(f"No deletion candidates found in: {repo_name}")
            continue

        # Iterate images to separate data and to generate a report.
        deletable_images = []
        for image_data in repo_candidates:
            # The 'image' is formatted for the ECR client, e.g. {"imageDigest": "sha256:e92e8...", "imageTag": "rel-2022.09.16"}
            image = image_data[0]
            num_bytes = image_data[1]

            deletable_images.append(image)
            total_bytes_deleted += num_bytes
            tag = image.get("imageTag", "untagged")
            if dry_run:
                deletion_report.append(
                    f"Dry run deletion candidate: {repo_name}/{tag} = {num_bytes} bytes"
                )
            else:
                deletion_report.append(f"Image deleted: {repo_name}/{tag} = {num_bytes} bytes")

        # Then, batch the deletions for the repository.
        total_images_deleted += len(deletable_images)
        if not dry_run:
            for btch in batch(deletable_images, n=99):
                client.batch_delete_image(repositoryName=repo_name, imageIds=btch)

    return {
        "num_images": total_images_deleted,
        "num_bytes": total_bytes_deleted,
        "deletion_report": deletion_report,
    }


def gb_str_from_bytes(num_bytes: int) -> str:
    return f"{num_bytes / (1024**3):.2f}"


def get_deployed_containers() -> list:
    try:
        df = get_oee_config_permutations()
    except OperationalError as e:
        raise RuntimeError(e)
    df = df[~df.site.isin(["sim", "hilsim", "TOR_DEN_1"])]
    all_versions = df["container_version"].unique().tolist()

    return all_versions


def matches_keep_pattern(tag: str) -> bool:
    for keep_pattern in TAG_KEEP_PATTERNS:
        if keep_pattern.match(tag):
            return True
    return False


def is_fielded(tag: str, repository: str, all_field_versions) -> bool:
    if repository is MFR and tag in all_field_versions:
        return True
    return False


def is_recent(push_time: datetime) -> bool:
    # push_time is in local timezone
    local_tz = pytz.timezone(LOCAL_TZ)
    cutoff_time = datetime.now(local_tz) - timedelta(days=KEEP_DAYS)
    return push_time >= cutoff_time


def report_deleted(deletion_data):
    deletion_data.sort()
    print("\n".join(deletion_data))


def report_skipped(categorized_images: dict, deployed_images: list) -> None:
    print("All images deployed in the field: " f"{deployed_images} ({len(deployed_images)} images)")
    for repo in categorized_images:
        per_repo_images = categorized_images[repo]
        recent = [f"Retained - Recent: {repo}: {tag}" for tag in per_repo_images["recent"]]
        fielded = [
            f"Retained - Deployed in the field: {repo}: {tag}" for tag in per_repo_images["fielded"]
        ]
        keep_pattern = [
            f"Retained - 'keep pattern' match: {repo}: {tag}"
            for tag in per_repo_images["keep_pattern"]
        ]

    for categorized in [recent, fielded, keep_pattern]:
        categorized.sort()
        print("\n".join(categorized))


if __name__ == "__main__":
    sys.exit(main())
