"""🏢 agentcompany — 역할별 모델·사고 강도 자동 배정(studio/agents/studio.py ROUTING)."""
from studio.agents import studio as ST


class Fake:
    model, effort = "claude-opus-5-5", "high"

    def __init__(self, fail_model=""):
        self.calls, self.fail_model = [], fail_model

    def structured(self, **kw):
        self.calls.append((kw.get("model"), kw.get("effort")))
        if self.fail_model and kw.get("model") == self.fail_model:
            raise RuntimeError(f"invalid model: {self.fail_model}")
        return {}


def test_auto_routes_by_role_and_bumps_long_context():
    fc = Fake()
    st = ST.Studio(fc, routing="auto")
    st.call("cut_editor", "x", "do")
    st.call("stock_pick", "x", "do")
    st.call("captions", "x" * (ST.BIG_CTX + 1), "do")
    assert fc.calls == [(ST.FABLE, "xhigh"), (ST.SONNET, "medium"), (ST.SONNET, "xhigh")]
    assert ST.route("director", ST.BIG_CTX * 2) == (ST.FABLE, "xhigh")   # max 는 자동으로 안 씀


def test_global_mode_and_file_override_win():
    fc = Fake()
    ST.Studio(fc).call("cut_editor", "x", "do")
    ST.Studio(fc, routing="auto", effort={"cut_editor": "low"}, models={"cut_editor": "m"}).call("cut_editor", "x", "do")
    assert fc.calls == [(None, "high"), ("m", "low")]


def test_unavailable_routed_model_falls_back_to_global():
    fc = Fake(fail_model=ST.FABLE)
    ST.Studio(fc, routing="auto").call("director", "x", "do")
    assert fc.calls == [(ST.FABLE, "xhigh"), (None, "high")]
