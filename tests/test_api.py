"""API tests: happy paths plus whole-request validation failures."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_clusters_zero_crossing_merge():
    payload = {
        "L": 360.0,
        "G": 10.0,
        "echoes": [
            {"position": 355.0, "amplitude": 80.0},
            {"position": 358.0, "amplitude": 120.0},
            {"position": 2.0, "amplitude": 90.0},
            {"position": 5.0, "amplitude": 60.0},
        ],
    }
    r = client.post("/clusters", json=payload)
    assert r.status_code == 200
    assert r.json() == {
        "clusters": [
            {
                "start": 355.0,
                "length": 10.0,
                "echo_count": 4,
                "peak_amplitude": 120.0,
                "peak_position": 358.0,
            }
        ]
    }


def test_clusters_multiple_sorted_by_start():
    payload = {
        "L": 360.0,
        "G": 15.0,
        "echoes": [
            {"position": 350.0, "amplitude": 40.0},
            {"position": 355.0, "amplitude": 60.0},
            {"position": 10.0, "amplitude": 55.0},
            {"position": 20.0, "amplitude": 50.0},
            {"position": 180.0, "amplitude": 70.0},
            {"position": 190.0, "amplitude": 65.0},
        ],
    }
    r = client.post("/clusters", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert [c["start"] for c in body["clusters"]] == [180.0, 350.0]
    assert body["clusters"][0]["length"] == 10.0
    assert body["clusters"][1] == {
        "start": 350.0,
        "length": 30.0,
        "echo_count": 4,
        "peak_amplitude": 60.0,
        "peak_position": 355.0,
    }


def _assert_422_with_loc(response, *path):
    assert response.status_code == 422
    body = response.json()
    assert "clusters" not in body  # never partial clusters on invalid input
    locs = [tuple(err["loc"]) for err in body["detail"]]
    assert ("body",) + path in locs


def test_empty_echoes_rejected():
    r = client.post("/clusters", json={"L": 360.0, "G": 10.0, "echoes": []})
    _assert_422_with_loc(r, "echoes")


def test_missing_echoes_rejected():
    r = client.post("/clusters", json={"L": 360.0, "G": 10.0})
    _assert_422_with_loc(r, "echoes")


@pytest.mark.parametrize("L", [0.0, -5.0])
def test_L_must_be_positive(L):
    r = client.post(
        "/clusters", json={"L": L, "G": 0.0, "echoes": [{"position": 0.0, "amplitude": 1.0}]}
    )
    _assert_422_with_loc(r, "L")


def test_G_negative_rejected():
    r = client.post(
        "/clusters", json={"L": 360.0, "G": -1.0, "echoes": [{"position": 1.0, "amplitude": 1.0}]}
    )
    _assert_422_with_loc(r, "G")


@pytest.mark.parametrize("G", [50.0, 60.0])
def test_G_must_be_less_than_half_L(G):
    r = client.post(
        "/clusters", json={"L": 100.0, "G": G, "echoes": [{"position": 10.0, "amplitude": 1.0}]}
    )
    _assert_422_with_loc(r, "G")


def test_position_negative_rejected():
    r = client.post(
        "/clusters",
        json={"L": 360.0, "G": 10.0, "echoes": [{"position": -0.5, "amplitude": 1.0}]},
    )
    _assert_422_with_loc(r, "echoes", 0, "position")


def test_position_equal_to_L_rejected():
    r = client.post(
        "/clusters",
        json={"L": 360.0, "G": 10.0, "echoes": [{"position": 360.0, "amplitude": 1.0}]},
    )
    _assert_422_with_loc(r, "echoes", 0, "position")


def test_position_beyond_L_locates_offending_index():
    r = client.post(
        "/clusters",
        json={
            "L": 100.0,
            "G": 10.0,
            "echoes": [
                {"position": 10.0, "amplitude": 1.0},
                {"position": 250.0, "amplitude": 2.0},
            ],
        },
    )
    _assert_422_with_loc(r, "echoes", 1, "position")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["L", "G"])
def test_non_finite_geometry_rejected(field, bad):
    raw = (
        '{"L": %s, "G": %s, "echoes": [{"position": 1.0, "amplitude": 1.0}]}'
        % (bad if field == "L" else "360.0", bad if field == "G" else "10.0")
    )
    r = client.post("/clusters", content=raw, headers={"content-type": "application/json"})
    _assert_422_with_loc(r, field)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_echo_values_rejected(bad):
    raw = '{"L": 360.0, "G": 10.0, "echoes": [{"position": %s, "amplitude": 1.0}]}' % bad
    r = client.post("/clusters", content=raw, headers={"content-type": "application/json"})
    _assert_422_with_loc(r, "echoes", 0, "position")
    raw = '{"L": 360.0, "G": 10.0, "echoes": [{"position": 1.0, "amplitude": %s}]}' % bad
    r = client.post("/clusters", content=raw, headers={"content-type": "application/json"})
    _assert_422_with_loc(r, "echoes", 0, "amplitude")


@pytest.mark.parametrize(
    "raw, expected_input",
    [
        # Regression: a NaN/Infinity input must surface as a locatable 422
        # with a valid JSON body, never as a 500.
        ('{"L": 360.0, "G": 10.0, "echoes": [{"position": NaN, "amplitude": 1.0}]}', "NaN"),
        ('{"L": 360.0, "G": 10.0, "echoes": [{"position": Infinity, "amplitude": 1.0}]}', "Infinity"),
        ('{"L": 360.0, "G": 10.0, "echoes": [{"position": 1.0, "amplitude": -Infinity}]}', "-Infinity"),
        ('{"L": NaN, "G": 10.0, "echoes": [{"position": 1.0, "amplitude": 1.0}]}', "NaN"),
        ('{"L": 360.0, "G": Infinity, "echoes": [{"position": 1.0, "amplitude": 1.0}]}', "Infinity"),
    ],
)
def test_non_finite_input_yields_valid_422_json(raw, expected_input):
    r = client.post("/clusters", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422
    body = r.json()  # must parse as JSON; a 500 would not carry detail
    assert "clusters" not in body
    detail = body["detail"]
    assert any(err.get("input") == expected_input for err in detail)


def test_unknown_field_rejected():
    r = client.post(
        "/clusters",
        json={
            "L": 360.0,
            "G": 10.0,
            "echoes": [{"position": 1.0, "amplitude": 1.0}],
            "debug": True,
        },
    )
    _assert_422_with_loc(r, "debug")


def test_missing_amplitude_rejected():
    r = client.post(
        "/clusters", json={"L": 360.0, "G": 10.0, "echoes": [{"position": 1.0}]}
    )
    _assert_422_with_loc(r, "echoes", 0, "amplitude")


def test_multiple_invalid_fields_all_reported():
    r = client.post(
        "/clusters",
        json={
            "L": 100.0,
            "G": 75.0,
            "echoes": [
                {"position": 10.0, "amplitude": 1.0},
                {"position": 100.0, "amplitude": 2.0},
                {"position": 250.0, "amplitude": 3.0},
            ],
        },
    )
    assert r.status_code == 422
    locs = [tuple(err["loc"]) for err in r.json()["detail"]]
    assert ("body", "G") in locs
    assert ("body", "echoes", 1, "position") in locs
    assert ("body", "echoes", 2, "position") in locs
