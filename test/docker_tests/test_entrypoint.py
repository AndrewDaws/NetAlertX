'''
Tests for the NetAlertX entrypoint.sh script.

These tests verify the behavior of the entrypoint script under various conditions,
such as environment variable settings and check skipping.
'''

import subprocess
import uuid
import pytest

IMAGE = "netalertx-test"


def _run_entrypoint(env: dict[str, str] | None = None, check_only: bool = True) -> subprocess.CompletedProcess[str]:
    """Run the entrypoint script in the test container with given environment."""
    name = f"netalertx-test-entrypoint-{uuid.uuid4().hex[:8]}".lower()
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "host", "--userns", "host",
        "--tmpfs", "/tmp:mode=777",
        "--cap-add", "NET_RAW", "--cap-add", "NET_ADMIN", "--cap-add", "NET_BIND_SERVICE",
    ]
    if env:
        for key, value in env.items():
            cmd.extend(["-e", f"{key}={value}"])
    if check_only:
        cmd.extend(["-e", "NETALERTX_CHECK_ONLY=1"])
    cmd.extend([
        "--entrypoint", "/bin/sh", IMAGE, "-c",
        "sh /entrypoint.sh"
    ])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


@pytest.mark.docker
@pytest.mark.feature_complete
def test_skip_tests_env_var():
    # If SKIP_TESTS=1 is set, the entrypoint should skip all startup checks and print a
    # message indicating checks are skipped.
    # There should be no check output, and the script should exit successfully.
    result = _run_entrypoint(env={"SKIP_TESTS": "1"}, check_only=True)
    assert "Skipping startup checks as SKIP_TESTS is set." in result.stdout
    assert " --> " not in result.stdout  # No check outputs
    assert result.returncode == 0


@pytest.mark.docker
@pytest.mark.feature_complete
def test_app_conf_override_from_graphql_port():
    # If GRAPHQL_PORT is set and APP_CONF_OVERRIDE is not set, the entrypoint should set
    # APP_CONF_OVERRIDE to a JSON string containing the GRAPHQL_PORT value and print a message
    # about it.
    # The script should exit successfully.
    result = _run_entrypoint(env={"GRAPHQL_PORT": "20212", "SKIP_TESTS": "1"}, check_only=True)
    assert 'Setting APP_CONF_OVERRIDE to {"GRAPHQL_PORT":"20212"}' in result.stdout
    assert result.returncode == 0


@pytest.mark.docker
@pytest.mark.feature_complete
def test_app_conf_override_not_overridden():
    # If both GRAPHQL_PORT and APP_CONF_OVERRIDE are set, the entrypoint should NOT override
    # APP_CONF_OVERRIDE or print a message about it.
    # The script should exit successfully.
    result = _run_entrypoint(env={
        "GRAPHQL_PORT": "20212",
        "APP_CONF_OVERRIDE": '{"OTHER":"value"}',
        "SKIP_TESTS": "1"
    }, check_only=True)
    assert 'Setting APP_CONF_OVERRIDE to' not in result.stdout
    assert result.returncode == 0


@pytest.mark.docker
@pytest.mark.feature_complete
def test_no_app_conf_override_when_no_graphql_port():
    # If GRAPHQL_PORT is not set, the entrypoint should NOT set or print APP_CONF_OVERRIDE.
    # The script should exit successfully.
    result = _run_entrypoint(env={"SKIP_TESTS": "1"}, check_only=True)
    assert 'Setting APP_CONF_OVERRIDE to' not in result.stdout
    assert result.returncode == 0