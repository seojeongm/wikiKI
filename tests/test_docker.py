"""
Docker tests: build and run validation.
Run with: pytest --docker
Completion criteria 4 & 5.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_TAG = "wikiki:test"


def _require_docker():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not found")
    result = subprocess.run(
        ["docker", "version"],
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        pytest.skip("Docker daemon not available")


@pytest.mark.docker
def test_docker_build_succeeds():
    """docker build completes without errors (criteria 4)."""
    _require_docker()
    try:
        result = subprocess.run(
            ["docker", "build", "-t", IMAGE_TAG, "."],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            cwd=PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("docker build timed out after 300s")
    assert result.returncode == 0, (
        f"docker build failed (exit {result.returncode})\nSTDERR:\n{result.stderr}"
    )


@pytest.mark.docker
def test_docker_run_receives_stream_events():
    """docker run outputs valid JSON stream events from Wikimedia (criteria 5)."""
    _require_docker()
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "-e", "MAX_EVENTS=3", IMAGE_TAG],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            cwd=PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("docker run timed out after 120s")
    assert result.returncode == 0, (
        f"docker run failed (exit {result.returncode})\nSTDERR:\n{result.stderr}"
    )

    lines = [ln.strip() for ln in result.stdout.strip().splitlines() if ln.strip()]
    assert len(lines) >= 3, f"Expected >=3 events, got {len(lines)}: {lines}"

    for line in lines:
        event = json.loads(line)  # raises if not valid JSON
        assert isinstance(event, dict)
