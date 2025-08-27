import sys
import base64
import random
import pytest

INSTALL_PATH = "/app"
sys.path.extend([f"{INSTALL_PATH}/front/plugins", f"{INSTALL_PATH}/server"])

from helper import get_setting_value, timeNowTZ
from api_server.api_server_start import app


@pytest.fixture(scope="session")
def api_token():
    return get_setting_value("API_TOKEN")


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def test_mac():
    # Generate a unique MAC for each test run
    return "AA:BB:CC:" + ":".join(f"{random.randint(0,255):02X}" for _ in range(3))


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def b64(sql: str) -> str:
    """Helper to base64 encode SQL"""
    return base64.b64encode(sql.encode("utf-8")).decode("utf-8")


# -----------------------------
# Device lifecycle via dbquery endpoints
# -----------------------------
def test_dbquery_create_device(client, api_token, test_mac):
    sql = f"""
        INSERT INTO Devices (devMac, devName, devVendor, devOwner, devFirstConnection, devLastConnection, devLastIP)
        VALUES ('{test_mac}', 'UnitTestDevice', 'TestVendor', 'UnitTest', '{timeNowTZ()}', '{timeNowTZ()}', '192.168.100.22' )
    """
    resp = client.post("/dbquery/write", json={"rawSql": b64(sql)}, headers=auth_headers(api_token))
    print(resp.json)
    print(resp)
    assert resp.status_code == 200
    assert resp.json.get("success") is True
    assert resp.json.get("affected_rows") == 1


def test_dbquery_read_device(client, api_token, test_mac):
    sql = f"SELECT * FROM Devices WHERE devMac = '{test_mac}'"
    resp = client.post("/dbquery/read", json={"rawSql": b64(sql)}, headers=auth_headers(api_token))
    assert resp.status_code == 200
    assert resp.json.get("success") is True
    results = resp.json.get("results")
    assert any(row["devMac"] == test_mac for row in results)


def test_dbquery_update_device(client, api_token, test_mac):
    sql = f"""
        UPDATE Devices
        SET devName = 'UnitTestDeviceRenamed'
        WHERE devMac = '{test_mac}'
    """
    resp = client.post("/dbquery/write", json={"rawSql": b64(sql)}, headers=auth_headers(api_token))
    assert resp.status_code == 200
    assert resp.json.get("success") is True
    assert resp.json.get("affected_rows") == 1

    # Verify update
    sql_check = f"SELECT devName FROM Devices WHERE devMac = '{test_mac}'"
    resp2 = client.post("/dbquery/read", json={"rawSql": b64(sql_check)}, headers=auth_headers(api_token))
    assert resp2.status_code == 200
    assert resp2.json.get("results")[0]["devName"] == "UnitTestDeviceRenamed"


def test_dbquery_delete_device(client, api_token, test_mac):
    sql = f"DELETE FROM Devices WHERE devMac = '{test_mac}'"
    resp = client.post("/dbquery/write", json={"rawSql": b64(sql)}, headers=auth_headers(api_token))
    assert resp.status_code == 200
    assert resp.json.get("success") is True
    assert resp.json.get("affected_rows") == 1

    # Verify deletion
    sql_check = f"SELECT * FROM Devices WHERE devMac = '{test_mac}'"
    resp2 = client.post("/dbquery/read", json={"rawSql": b64(sql_check)}, headers=auth_headers(api_token))
    assert resp2.status_code == 200
    assert resp2.json.get("results") == []
