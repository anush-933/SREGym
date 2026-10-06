from mcp_server import loki_server
from sregym.service.agent_visibility_policy import mentions_brand


class FakeResponse:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def test_loki_tools_hide_chaos_streams_and_label_values(monkeypatch):
    class FakeClient:
        def __init__(self, _url):
            pass

        def make_request(self, _method, url, **_kwargs):
            if url.endswith("query_range"):
                return FakeResponse(
                    {
                        "status": "success",
                        "data": {
                            "result": [
                                {
                                    "stream": {"namespace": "chaos-mesh", "pod": "chaos-controller-manager"},
                                    "values": [["1000000000", "controller applied PodChaos"]],
                                },
                                {
                                    "stream": {"namespace": "astronomy-shop", "pod": "checkout"},
                                    "values": [
                                        ["1000000000", "checkout completed"],
                                        ["2000000000", "chaos-mesh injected a disruption"],
                                    ],
                                },
                            ]
                        },
                    }
                )
            return FakeResponse({"status": "success", "data": ["chaos-mesh", "astronomy-shop"]})

    monkeypatch.setattr(loki_server, "ObservabilityClient", FakeClient)

    logs = loki_server.get_logs.fn('{namespace=~".+"}')
    values = loki_server.get_label_values.fn("namespace")

    assert "checkout completed" in logs
    assert "chaos-mesh" not in logs
    assert "chaos-mesh" not in values
    assert "astronomy-shop" in values


def test_loki_tools_neutralize_harness_branding_without_dropping_streams(monkeypatch):
    class FakeClient:
        def __init__(self, _url):
            pass

        def make_request(self, _method, url, **_kwargs):
            if url.endswith("query_range"):
                return FakeResponse(
                    {
                        "status": "success",
                        "data": {
                            "result": [
                                {
                                    "stream": {"namespace": "sregym-mcp-abc", "pod": "sregym-mcp-abc"},
                                    "values": [["1000000000", "mcp server ready in ghcr.io/sregym/sregym-mcp"]],
                                }
                            ]
                        },
                    }
                )
            return FakeResponse({"status": "success", "data": ["namespace", "sregym-agent"]})

    monkeypatch.setattr(loki_server, "ObservabilityClient", FakeClient)

    logs = loki_server.get_logs.fn('{namespace=~".+"}')
    values = loki_server.get_label_values.fn("namespace")

    # The record itself is still useful, so it is rewritten rather than removed.
    assert "mcp server ready" in logs
    assert "evaluation" in logs
    assert not mentions_brand(logs)
    assert "evaluation-agent" in values
    assert not mentions_brand(values)
