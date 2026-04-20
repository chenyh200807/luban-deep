from __future__ import annotations

import httpx

from deeptutor.services.observability.surface_ack_smoke import run_surface_ack_smoke


def test_run_surface_ack_smoke_posts_events_and_verifies_coverage() -> None:
    requests_seen: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = __import__("json").loads(request.content.decode("utf-8"))
            requests_seen.append((request.method, str(request.url), payload))
            return httpx.Response(
                202,
                json={
                    "ok": True,
                    "accepted": True,
                    "status": "accepted",
                    "event_id": payload["event_id"],
                    "surface": payload["surface"],
                    "event_name": payload["event_name"],
                },
            )

        requests_seen.append((request.method, str(request.url), {}))
        return httpx.Response(
            200,
            json={
                "surface_events": {
                    "coverage": [
                        {
                            "surface": "web",
                            "start_turn_sent": 1,
                            "first_visible_content_rendered": 1,
                            "done_rendered": 1,
                            "surface_render_failed": 0,
                            "first_render_coverage_ratio": 1.0,
                            "done_render_coverage_ratio": 1.0,
                        }
                    ]
                }
            },
        )

    payload = run_surface_ack_smoke(
        api_base_url="http://127.0.0.1:8001",
        surface="web",
        session_id="session-smoke-1",
        turn_id="turn-smoke-1",
        transport=httpx.MockTransport(handler),
    )

    assert payload["passed"] is True
    assert payload["surface"] == "web"
    assert payload["missing_requirements"] == []
    assert payload["coverage"]["first_render_coverage_ratio"] == 1.0
    assert payload["coverage"]["done_render_coverage_ratio"] == 1.0
    assert [item["event_name"] for item in payload["posted_events"]] == [
        "start_turn_sent",
        "first_visible_content_rendered",
        "done_rendered",
    ]
    assert [item[0] for item in requests_seen] == ["POST", "POST", "POST", "GET"]

