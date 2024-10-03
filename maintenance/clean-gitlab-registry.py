#!/usr/bin/env python3
"""

Environment Variables:
  Environment variables are used to facilitate CI pipelines rather than command line parameters.

  Imported:
    DRY_RUN: With the value of "true", deletion candidates are identified but not deleted from
             the GitLab registry. If undefined or "false", images are deleteed.
  
  Required in the Environment but not Imported:
    PG_USER: The user to query the database for releases deployed to robots in the field.
    PGPASSWORD: The password for PG_USER
    RDSHOST: The database server name.
"""

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from psycopg2 import OperationalError

from redacted_common_py import constants
from redacted_cli.util.docker_util import RegistryClient
from dataapi.robots.oee import get_oee_config_permutations

MFR = "redacted/main-full-runtime"
REGISTRY_URL = "gitlab-registry"
REPO_PREFIXES = [
    "redacted/arm",
    "redacted/hwif",
    "redacted/fiddle",
    "redacted/gong",
    "redacted/main",
]
TAG_KEEP_PATTERNS = [
    re.compile(r"^.*latest$"),
    re.compile(r"^dev_nightly$"),
    re.compile(r"^rel-\d{4}\.\d{2}\.\d{2}(?:_\d+)?$"),
    re.compile(r"^rel-\d{4}\.\d{2}\.\d{2}_nightly$"),
]
KEEP_DAYS = 30
DATE_PATTERN = r".*(\d{4})\D?(0[1-9]|1[0-2])\D?([12]\d|0[1-9]|3[01]).*$"


def main() -> int:
    errs = 0

    dry_run = os.getenv("DRY_RUN", "False").lower() in ("1", "t", "true", "y", "yes")

    client = RegistryClient(hostname=REGISTRY_URL)
    repository_names = find_repo_names(client)
    repository_names.sort()
    try:
        all_field_versions = get_deployed_containers()
    except RuntimeError as e:
        print(f"Database query failed: {e}")
        errs += 1

    if not errs:
        categorized_images = categorize_repo_images(client, repository_names, all_field_versions)
        print("Analyzing deletion candidates. This can take awhile.")
        delete_targets, reclaimed_bytes = delete_images(client, categorized_images, dry_run)

        report_skipped(categorized_images, all_field_versions)
        report_deleted(delete_targets, reclaimed_bytes, dry_run)

    if errs:
        print("Fatal errors incurred. Script exiting.")

    return errs


def categorize_repo_images(
    client: RegistryClient, repository_names: list, all_field_versions: list
) -> dict:
    categorized_repos = {}
    for repo in repository_names:
        print(f"Evaluating repository: {repo}")
        categorized_repos[repo] = {
            "recent": [],
            "fielded": [],
            "prefixed": [],
            "deletable": [],
            "untagged": [],
        }
        tags = client.list_tags(repo)
        if tags:
            categorized_repos[repo]["untagged"] = False
            for tag in tags:
                if has_prefix(tag):
                    categorized_repos[repo]["prefixed"].append(tag)
                    continue

                if is_fielded(tag, repo, all_field_versions):
                    categorized_repos[repo]["fielded"].append(tag)
                    continue

                if is_recent(tag):
                    categorized_repos[repo]["recent"].append(tag)
                    continue

                categorized_repos[repo]["deletable"].append(tag)
        else:
            categorized_repos[repo]["untagged"] = True

        # For nicer reports
        for category in ["prefixed", "fielded", "recent", "deletable"]:
            categorized_repos[repo][category].sort()

    return categorized_repos


def delete_images(client: RegistryClient, categorized_images: dict, dry_run: bool):
    # num_images_deleted = 0
    delete_targets = {}
    all_layers = {}
    for repo, images in categorized_images.items():
        images_deletable = images["deletable"]
        images_deletable.sort()
        for image in images_deletable:
            image_layers = get_image_layers(client, repo, image)
            # Layers are deduplicated by overwriting shared layer infomation
            # with the same layer information from a different image.
            all_layers.update(image_layers)
            image_bytes = sum(image_layers.values())
            delete_targets[f"{repo}:{image}"] = image_bytes
            if not dry_run:
                client.delete(repo, image)

    # Deduplicated bytes reclaimed cannot be easily calcuated outsie of this function. Return explicitly.
    # But the sum of the per-image bytes is not deduplicated.
    # return num_images_deleted, sum(all_layers.values())
    return delete_targets, sum(all_layers.values())


def find_repo_names(client: RegistryClient) -> list:
    repositories = client.list_repositories()
    return [r for r in repositories if any([r.startswith(p) for p in REPO_PREFIXES])]


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


def get_image_layers(client: RegistryClient, repository_name: str, image: str) -> int:
    layer_info = {}
    details = client.get_details(repository_name, image)
    if details:
        # details is a tuple similar to an http response (header, body) when successful.
        layers = details[1]["layers"]
        if layers:
            # The layers information can contain duplicate entries.
            # De-dupe by overwriting duplicated entries.
            for layer in layers:
                layer_info[layer["digest"]] = layer["size"]
    return layer_info


def get_image_size(client: RegistryClient, repository_name: str, image: str) -> int:
    layers = get_image_layers(client, repository_name, image)
    if layers:
        return sum(layers.values())

    return 0


def has_prefix(tag: str) -> bool:
    for prefix_pattern in TAG_KEEP_PATTERNS:
        if prefix_pattern.match(tag):
            return True
    return False


def is_fielded(tag: str, repository: str, all_field_versions) -> bool:
    if repository == MFR and tag in all_field_versions:
        return True
    return False


def is_recent(tag: str) -> bool:
    pushed_at = None
    match = re.search(DATE_PATTERN, tag)
    if match:
        pushed_at = datetime.strptime(
            f"{match.group(1)}.{match.group(2)}.{match.group(3)}",
            "%Y.%m.%d",
        )
        # Dates are in local time.
        # pushed_at is tz-naive
        cutoff_date = datetime.now() - timedelta(days=KEEP_DAYS)
        if pushed_at and pushed_at >= cutoff_date:
            return True

    return False


def report_deleted(delete_targets: dict, total_bytes: int, dry_run: bool):
    report_lines = []
    for repo_tag, bytes_deleted in delete_targets.items():
        image_gb = gb_str_from_bytes(bytes_deleted)
        if dry_run:
            report_lines.append(f"Deleted (simulated) - {repo_tag}: size = {image_gb} GB")
        else:
            report_lines.append(f"Deleted - {repo_tag}: size = {image_gb} GB")

    print("\n".join(report_lines))

    num_images = len(delete_targets)
    gb_deleted = gb_str_from_bytes(total_bytes)
    if dry_run:
        print(f"{num_images} images, " f"({gb_deleted} GB) would be reclaimed.")
    else:
        print(f"{num_images} images deleted and " f"({gb_deleted} GB) were reclaimed.")


def report_skipped(categorized_images: dict, deployed_images) -> None:
    print("All images deployed in the field: " f"{deployed_images} ({len(deployed_images)} images)")

    recent = []
    fielded = []
    prefixed = []
    untagged = []
    for repo in categorized_images.keys():
        per_repo_images = categorized_images[repo]
        recent += [f"Retained - Recent: {repo}: {tag}" for tag in per_repo_images["recent"]]
        fielded += [
            f"Retained - Deployed in the field: {repo}: {tag}" for tag in per_repo_images["fielded"]
        ]
        prefixed += [
            f"Retained - Prefix match: {repo}: {tag}" for tag in per_repo_images["prefixed"]
        ]
        if per_repo_images["untagged"]:
            untagged.append(f"Retained - No tags found in repo: {repo}")

    for categorized in [recent, fielded, prefixed, untagged]:
        categorized.sort()
        print("\n".join(categorized))


if __name__ == "__main__":
    sys.exit(main())
