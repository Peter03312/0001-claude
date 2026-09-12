"""One-shot acceptance suite for the defect clustering API.

Runs against a live API (default http://localhost:8000, override with
API_BASE_URL) and exits non-zero if any check fails.  Observes:
zero-crossing merge, inclusive threshold boundary, stable start/length,
echo counts, peak positions, and whole-request validation errors.
"""

from __future__ import annotations

import os
import sys
import time

import httpx

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")

_failures: list[str] = []


def check(name: str, actual, expected) -> None:
    if actual == expected:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}\n  expected: {expected}\n  actual:   {actual}")
        _failures.append(name)


def wait_for_api(client: httpx.Client, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            if client.get("/health").status_code == 200:
                print(f"API healthy at {BASE_URL}")
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            print(f"API at {BASE_URL} did not become healthy within {timeout}s")
            raise SystemExit(1)
        time.sleep(0.5)


def scenario_zero_crossing_merge(client: httpx.Client) -> None:
    # Defect on the zero seam: echoes at 355/358 and 2/5 must form ONE cluster.
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
    check("zero-crossing: status 200", r.status_code, 200)
    check(
        "zero-crossing: split echoes merged into one cluster",
        r.json(),
        {
            "clusters": [
                {
                    "start": 355.0,
                    "length": 10.0,
                    "echo_count": 4,
                    "peak_amplitude": 120.0,
                    "peak_position": 358.0,
                }
            ]
        },
    )


def scenario_threshold_boundary(client: httpx.Client) -> None:
    # Gap exactly G merges; gap G+1 splits.
    payload = {
        "L": 100.0,
        "G": 10.0,
        "echoes": [
            {"position": 10.0, "amplitude": 50.0},
            {"position": 20.0, "amplitude": 60.0},
            {"position": 50.0, "amplitude": 70.0},
            {"position": 61.0, "amplitude": 80.0},
        ],
    }
    r = client.post("/clusters", json=payload)
    check(
        "threshold: gap == G merges, gap > G splits",
        r.json(),
        {
            "clusters": [
                {"start": 10.0, "length": 10.0, "echo_count": 2,
                 "peak_amplitude": 60.0, "peak_position": 20.0},
                {"start": 50.0, "length": 0.0, "echo_count": 1,
                 "peak_amplitude": 70.0, "peak_position": 50.0},
                {"start": 61.0, "length": 0.0, "echo_count": 1,
                 "peak_amplitude": 80.0, "peak_position": 61.0},
            ]
        },
    )
    # Wrap distance exactly G merges across zero.
    payload = {
        "L": 360.0,
        "G": 10.0,
        "echoes": [
            {"position": 355.0, "amplitude": 100.0},
            {"position": 5.0, "amplitude": 90.0},
        ],
    }
    r = client.post("/clusters", json=payload)
    check(
        "threshold: wrap gap == G merges across zero",
        r.json(),
        {
            "clusters": [
                {"start": 355.0, "length": 10.0, "echo_count": 2,
                 "peak_amplitude": 100.0, "peak_position": 355.0}
            ]
        },
    )


def scenario_stable_start_and_length(client: httpx.Client) -> None:
    # Zero-crossing cluster keeps a stable start/length next to a decoy
    # cluster, and repeated calls return identical results.
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
    expected = {
        "clusters": [
            {"start": 180.0, "length": 10.0, "echo_count": 2,
             "peak_amplitude": 70.0, "peak_position": 180.0},
            {"start": 350.0, "length": 30.0, "echo_count": 4,
             "peak_amplitude": 60.0, "peak_position": 355.0},
        ]
    }
    r1 = client.post("/clusters", json=payload)
    r2 = client.post("/clusters", json=payload)
    check("stable: status 200", r1.status_code, 200)
    check("stable: zero-crossing start/length", r1.json(), expected)
    check("stable: repeated call identical", r2.json(), r1.json())


def scenario_echo_count_and_peak(client: httpx.Client) -> None:
    # Same-position echoes collapse to the strongest (count 2, not 3);
    # amplitude ties resolve to the smallest position.
    payload = {
        "L": 500.0,
        "G": 20.0,
        "echoes": [
            {"position": 100.0, "amplitude": 50.0},
            {"position": 100.0, "amplitude": 70.0},
            {"position": 110.0, "amplitude": 60.0},
            {"position": 300.0, "amplitude": 90.0},
            {"position": 310.0, "amplitude": 90.0},
        ],
    }
    r = client.post("/clusters", json=payload)
    check(
        "echo count after dedup and peak position on amplitude tie",
        r.json(),
        {
            "clusters": [
                {"start": 100.0, "length": 10.0, "echo_count": 2,
                 "peak_amplitude": 70.0, "peak_position": 100.0},
                {"start": 300.0, "length": 10.0, "echo_count": 2,
                 "peak_amplitude": 90.0, "peak_position": 300.0},
            ]
        },
    )


def scenario_validation(client: httpx.Client) -> None:
    cases = [
        ("empty echo array", {"L": 360.0, "G": 10.0, "echoes": []}, "echoes"),
        ("G >= L/2", {"L": 100.0, "G": 50.0,
                      "echoes": [{"position": 10.0, "amplitude": 1.0}]}, "G"),
        ("position >= L", {"L": 100.0, "G": 10.0,
                           "echoes": [{"position": 100.0, "amplitude": 1.0}]}, "position"),
        ("negative position", {"L": 100.0, "G": 10.0,
                               "echoes": [{"position": -1.0, "amplitude": 1.0}]}, "position"),
        ("L not positive", {"L": 0.0, "G": 0.0,
                            "echoes": [{"position": 0.0, "amplitude": 1.0}]}, "L"),
    ]
    for name, payload, field in cases:
        r = client.post("/clusters", json=payload)
        check(f"validation: {name} -> 422", r.status_code, 422)
        body = r.json()
        check(f"validation: {name} has no partial clusters", "clusters" in body, False)
        locs = [err.get("loc", []) for err in body.get("detail", [])]
        check(f"validation: {name} locates '{field}'", any(field in loc for loc in locs), True)
    # Non-finite numbers are rejected even though JSON parses them, and the
    # 422 body must stay valid, locatable JSON (never a 500).
    r = client.post(
        "/clusters",
        content='{"L": 360.0, "G": 10.0, "echoes": [{"position": NaN, "amplitude": 1.0}]}',
        headers={"content-type": "application/json"},
    )
    check("validation: NaN position -> 422", r.status_code, 422)
    body = r.json()
    check("validation: NaN has no partial clusters", "clusters" in body, False)
    locs = [err.get("loc", []) for err in body.get("detail", [])]
    check("validation: NaN locates 'position'", any("position" in loc for loc in locs), True)


def main() -> int:
    print(f"Running acceptance checks against {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        wait_for_api(client)
        scenario_zero_crossing_merge(client)
        scenario_threshold_boundary(client)
        scenario_stable_start_and_length(client)
        scenario_echo_count_and_peak(client)
        scenario_validation(client)
    if _failures:
        print(f"\n{len(_failures)} acceptance check(s) FAILED")
        return 1
    print("\nAll acceptance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
