"""The benchmark's own name must not reach the agent through any channel.

Frontier models already have prior knowledge of SREGym, so one branded string in
a pod image, a kubeconfig context, or an agent environment variable gives the run
away and destroys fidelity. These tests pin the neutral names that replace it.
"""

from pathlib import Path

import pytest
import yaml

from clients.harness.problem_id import HARNESS_ARTIFACT_ID_ENV, HARNESS_PROBLEM_ID_ENV
from sregym.service.agent_visibility_policy import (
    BRAND_NEUTRAL_TOKEN,
    filter_namespace_list,
    filter_resource_list,
    mentions_brand,
    neutralize_brand,
)
from sregym.service.container_runner import (
    AGENT_APPS_ROOT,
    AGENT_INSTALL_SCRIPTS_ROOT,
    AGENT_RUNTIME_ROOT,
    DEFAULT_AGENT_IMAGE,
    LOCAL_AGENT_IMAGE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
K8S_DIR = REPO_ROOT / "mcp_server/k8s"


def _visible(items):
    return filter_resource_list({"items": items}, set(), {})["items"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ghcr.io/sregym/sregym-mcp:latest", "ghcr.io/evaluation/evaluation-mcp:latest"),
        ("sregym-agent-base:latest", "evaluation-agent-base:latest"),
        ("/opt/sregym/results", "/opt/evaluation/results"),
        ("SREGym", "evaluation"),
        ("SREGYM", "evaluation"),
        ("sregymer", "evaluationer"),
        ("sregym-sregym", "evaluation-evaluation"),
        ("registry.k8s.io/pause:3.9", "registry.k8s.io/pause:3.9"),
        ("", ""),
    ],
)
def test_neutralize_brand_rewrites_embedded_case_insensitive_matches(value, expected):
    # Substring matching is deliberate: image references and annotation keys embed
    # the marker inside larger identifiers, so word boundaries would miss them.
    assert neutralize_brand(value) == expected
    assert mentions_brand(value) is (value != expected)


def test_pod_images_lose_the_harness_registry_org():
    pod = {
        "metadata": {"name": "mcp-server", "namespace": "evaluation"},
        "spec": {
            "containers": [{"image": "ghcr.io/sregym/sregym-mcp:latest"}],
            "initContainers": [{"image": "ghcr.io/sregym/setup:v1"}],
            "ephemeralContainers": [{"image": "sregym-debug:latest"}],
        },
    }

    spec = _visible([pod])[0]["spec"]

    assert spec["containers"][0]["image"] == "ghcr.io/evaluation/evaluation-mcp:latest"
    assert spec["initContainers"][0]["image"] == "ghcr.io/evaluation/setup:v1"
    assert spec["ephemeralContainers"][0]["image"] == "evaluation-debug:latest"


def test_workload_template_images_are_neutralized():
    deployment = {
        "metadata": {"name": "mcp-server", "namespace": "evaluation"},
        "spec": {"template": {"spec": {"containers": [{"image": "ghcr.io/sregym/sregym-mcp:latest"}]}}},
    }

    result = _visible([deployment])[0]

    assert result["spec"]["template"]["spec"]["containers"][0]["image"] == "ghcr.io/evaluation/evaluation-mcp:latest"


def test_published_harness_images_are_neutralized_even_though_they_cannot_be_renamed():
    # The published org is release infrastructure, so the reference stays in the
    # repo; a pod spec exposing it must still not reach the agent branded.
    pod = {"metadata": {"name": "agent"}, "spec": {"containers": [{"image": DEFAULT_AGENT_IMAGE}]}}

    image = _visible([pod])[0]["spec"]["containers"][0]["image"]

    assert image != DEFAULT_AGENT_IMAGE
    assert not mentions_brand(image)
    assert image.startswith("ghcr.io/evaluation/agent-base:")


def test_metadata_names_labels_and_annotations_are_neutralized():
    resource = {
        "metadata": {
            "name": "sregym-mcp-abc123",
            "labels": {"app.kubernetes.io/part-of": "sregym", "team": "platform"},
            "annotations": {"sregym.io/note": "owned by SREGym", "team": "platform"},
        }
    }

    metadata = _visible([resource])[0]["metadata"]

    assert metadata["name"] == "evaluation-mcp-abc123"
    assert metadata["labels"] == {"app.kubernetes.io/part-of": "evaluation", "team": "platform"}
    assert metadata["annotations"] == {"evaluation.io/note": "owned by evaluation", "team": "platform"}


def test_brand_rewrite_does_not_resurrect_chaos_bookkeeping():
    resource = {
        "metadata": {
            "annotations": {"chaos-mesh.org/injected": "true", "sregym.io/keep": "value"},
            "managedFields": [{"manager": "chaos-controller-manager"}, {"manager": "sregym-operator"}],
        }
    }

    metadata = filter_resource_list({"items": [resource]}, {"chaos-mesh"}, {})["items"][0]["metadata"]

    assert metadata["annotations"] == {"evaluation.io/keep": "value"}
    assert metadata["managedFields"] == [{"manager": "evaluation-operator"}]


def test_table_rows_are_neutralized_in_both_cells_and_object():
    table = {
        "rows": [
            {
                "cells": ["sregym-mcp-abc123", "evaluation", "1/1"],
                "object": {"metadata": {"name": "sregym-mcp-abc123", "namespace": "evaluation"}},
            }
        ]
    }

    row = filter_resource_list(table, set(), {})["rows"][0]

    assert row["cells"] == ["evaluation-mcp-abc123", "evaluation", "1/1"]
    assert row["object"]["metadata"]["name"] == "evaluation-mcp-abc123"


def test_namespace_list_is_neutralized():
    listing = {
        "items": [{"metadata": {"name": "sregym", "labels": {"app.kubernetes.io/part-of": "sregym"}}}],
        "rows": [{"cells": ["sregym"], "object": {"metadata": {"name": "sregym"}}}],
    }

    result = filter_namespace_list(listing, set())

    assert result["items"][0]["metadata"]["name"] == BRAND_NEUTRAL_TOKEN
    assert result["items"][0]["metadata"]["labels"] == {"app.kubernetes.io/part-of": BRAND_NEUTRAL_TOKEN}
    assert result["rows"][0]["cells"] == [BRAND_NEUTRAL_TOKEN]
    assert result["rows"][0]["object"]["metadata"]["name"] == BRAND_NEUTRAL_TOKEN


def test_agent_runtime_paths_and_local_image_are_neutral():
    # The agent lists /opt, prints $PYTHONPATH and sees its own image reference.
    for value in (AGENT_RUNTIME_ROOT, AGENT_APPS_ROOT, AGENT_INSTALL_SCRIPTS_ROOT, LOCAL_AGENT_IMAGE):
        assert not mentions_brand(value), value
    assert f"{AGENT_RUNTIME_ROOT}/apps" == AGENT_APPS_ROOT
    assert f"{AGENT_RUNTIME_ROOT}/install-scripts" == AGENT_INSTALL_SCRIPTS_ROOT


def test_agent_artifact_env_vars_do_not_spell_the_benchmark():
    # AgentLauncher re-injects these into the agent container's environment.
    assert HARNESS_ARTIFACT_ID_ENV == "HARNESS_ARTIFACT_ID"
    assert HARNESS_PROBLEM_ID_ENV == "HARNESS_PROBLEM_ID"


@pytest.mark.parametrize(
    "name",
    ["namespace.yaml", "deployment.yaml", "service.yaml", "serviceaccount.yaml", "clusterrolebinding.yaml"],
)
def test_mcp_manifests_carry_no_branded_namespace_or_name(name):
    text = (K8S_DIR / name).read_text()

    assert "namespace: sregym" not in text
    assert not mentions_brand(yaml.safe_load(text)["metadata"]["name"])


def test_harness_namespace_agrees_across_manifests_and_client():
    from sregym.service.cluster_state import PROTECTED_NAMESPACES
    from sregym.service.mcp_server import MCP_NAMESPACE

    kustomization = yaml.safe_load((K8S_DIR / "kustomization.yaml").read_text())
    binding = yaml.safe_load((K8S_DIR / "clusterrolebinding.yaml").read_text())

    assert kustomization["namespace"] == MCP_NAMESPACE
    assert binding["subjects"][0]["namespace"] == MCP_NAMESPACE
    # Baseline reconciliation must not treat the MCP namespace as scratch state.
    assert MCP_NAMESPACE in PROTECTED_NAMESPACES


def test_agent_image_keeps_no_branded_path_or_vendored_harness_source():
    dockerfile = (REPO_ROOT / "docker/agents/Dockerfile").read_text()

    assert not mentions_brand(dockerfile)
    assert f'ENV PYTHONPATH="{AGENT_RUNTIME_ROOT}"' in dockerfile
    # The dormant get_app_class_by_name() was the only reason to vendor sregym/.
    assert "COPY sregym/" not in dockerfile


def test_image_audit_exclusions_track_the_neutral_placeholder_names():
    source = (REPO_ROOT / "docker/audit_images.py").read_text()

    assert f'"{LOCAL_AGENT_IMAGE}"' in source
    assert '"evaluation-mcp:latest"' in source
    assert "sregym-agent-base:latest" not in source
    assert '"sregym:latest"' not in source
