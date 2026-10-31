"""The run harness with no network: the model is replaced by a scripted sequence of calls."""

import json
from types import SimpleNamespace

import pytest

from asasked import llm_extract
from asasked.harness import agent as agent_mod
from asasked.harness.agent import AGENTS, AgentSpec, parse_agent
from asasked.harness.run import run_task, score
from asasked.harness.tasks import PILOT

TASKS = {t.id: t for t in PILOT}


class _StubUser:
    """A simulator with no network: one phrase for any question."""

    model, reply = "stub", "Then don't buy anything, I'll wait."

    def __init__(self, request, persona):
        self.history, self.errors = [], []

    def __call__(self, question):
        self.history.append({"question": question, "reply": self.reply})
        return self.reply


@pytest.fixture(autouse=True)
def _no_network_user(monkeypatch):
    monkeypatch.setattr("asasked.harness.run.SimulatedUser", _StubUser)


def _vi_available():
    try:
        import asasked.vi_runner  # noqa: F401
    except SystemExit:
        return False
    return True


needs_vi = pytest.mark.skipif(not _vi_available(), reason="no verifiable-intent clone")


# ---------------------------------------------------------------------------
# Scoring by the label
# ---------------------------------------------------------------------------


def test_score_right_purchase():
    t = TASKS["pilot-refund-variant"]
    s = score(t, [("ASI-GELRESOLUTION9-42-BLA-COU", 1)], True, [])
    assert s == {"as_asked": True, "outcome": "as_asked", "vi_passed_but_wrong": False,
                 "asked": False, "asked_when_needed": False}


def test_score_final_sale_twin_is_wrong_although_paid():
    t = TASKS["pilot-refund-variant"]
    s = score(t, [("ASI-GELRESOLUTION9-42-BLA-OUT", 1)], True, [])
    assert not s["as_asked"] and s["vi_passed_but_wrong"]
    assert s["outcome"] == "wrong_purchase"
    assert score(t, None, False, [])["outcome"] == "stopped_short"


def test_score_quantity_counts():
    t = TASKS["pilot-couple-of-cans"]
    sku = next(iter(t.ok_skus))
    assert score(t, [(sku, 2)], True, [])["as_asked"]
    assert not score(t, [(sku, 4)], True, [])["as_asked"]
    four_pack = "PEN-CHAMPIONSHIP-12B-YEL-COU"
    assert not score(t, [(four_pack, 1)], True, [])["as_asked"]


def test_score_no_purchase_is_right_when_nothing_fits():
    t = TASKS["pilot-out-of-stock"]
    s = score(t, None, False, ["Size 45 is out of stock, OK to wait?"])
    assert s["as_asked"] and s["asked_when_needed"]
    assert not score(t, [("NIK-VAPORPRO2-44-WHI-COU", 1)], True, [])["as_asked"]


def test_declined_order_counts_as_nothing_bought():
    t = TASKS["pilot-final-sale-only"]
    assert score(t, [("BAB-PUREAERO98-412-BLA-OUT", 1)], False, [])["as_asked"]


def test_parse_agent():
    assert parse_agent("claude-sonnet-5") is AGENTS["claude-sonnet-5"]
    spec = parse_agent("openai_compat:qwen/qwen3.8-max")
    assert (spec.provider, spec.model) == ("openai_compat", "qwen/qwen3.8-max")
    with pytest.raises(ValueError):
        parse_agent("nope")


# ---------------------------------------------------------------------------
# The agent loop with a mocked model
# ---------------------------------------------------------------------------


def _block(**kw):
    return SimpleNamespace(**kw, model_dump=lambda exclude_none=True: dict(kw))


def _tool_use(i, name, args):
    return _block(type="tool_use", id=f"t{i}", name=name, input=args)


class _ScriptedClaude:
    """Answers with preset steps and remembers what it was sent."""

    def __init__(self, steps):
        self.steps, self.seen = list(steps), []
        self.messages = self

    def create(self, **kwargs):
        self.seen.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        blocks, stop = self.steps.pop(0)
        return SimpleNamespace(content=blocks, stop_reason=stop,
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def _claude(monkeypatch, steps):
    anthropic = pytest.importorskip("anthropic")
    fake = _ScriptedClaude(steps)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    return fake


@needs_vi
def test_claude_loop_buys_and_is_scored(monkeypatch):
    sku = "ASI-GELRESOLUTION9-42-BLA-OUT"   # the cheap twin with no returns
    fake = _claude(monkeypatch, [
        ([_tool_use(1, "search_products", {"query": "asics gel-resolution 42 black"})], "tool_use"),
        ([_tool_use(2, "add_to_cart", {"sku": sku}),
          _tool_use(3, "checkout", {"confirm": True})], "tool_use"),
        ([_block(type="text", text="Bought them.")], "end_turn"),
    ])
    rec = run_task(AGENTS["claude-sonnet-5"], TASKS["pilot-refund-variant"])

    assert rec["stop"] == "done" and rec["steps"] == 3
    assert rec["order"]["placed"] and rec["order"]["purchase"] == [(sku, 1)]
    assert rec["score"]["vi_passed_but_wrong"]
    assert rec["engine"]["coherent"] is False and rec["engine"]["agrees_with_label"]
    assert [f["code"] for f in rec["engine"]["findings"]] == ["refund"]
    # two tool results came back in one message
    last_user = fake.seen[2][-1]
    assert last_user["role"] == "user" and len(last_user["content"]) == 2
    assert rec["input_tokens"] == 30 and rec["final_text"] == "Bought them."


def test_claude_loop_stops_at_max_steps(monkeypatch):
    _claude(monkeypatch, [([_tool_use(i, "view_cart", {})], "tool_use") for i in range(5)])
    session = SimpleNamespace(call=lambda name, args: {"items": []}, tools=lambda: [])
    res = agent_mod.run_agent(AGENTS["claude-sonnet-5"], session, "hi", max_steps=3)
    assert res.stop == "max_steps" and res.steps == 3


def test_transport_error_is_not_a_score(monkeypatch):
    anthropic = pytest.importorskip("anthropic")

    def boom(**kw):
        raise agent_mod.AgentError("HTTP 503 from Claude: down")

    monkeypatch.setattr(agent_mod, "_loop_anthropic", lambda *a: boom())
    rec = run_task(AGENTS["claude-sonnet-5"], TASKS["pilot-vague"])
    assert rec["stop"] == "error" and rec["score"] is None and "503" in rec["error"]
    assert anthropic  # the package is there, the error is about transport


def test_openai_loop_asks_then_stops(monkeypatch):
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_BASE_URL", "https://proxy.test/v1")
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_API_KEY", "k")
    replies = [
        {"choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "ask_user", "arguments": '{"question": "Budget?"}'},
            }]}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        {"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "Nothing in stock, did not buy."}}]},
    ]
    sent = []

    def fake_post(url, body, api_key=None):
        sent.append(json.loads(json.dumps(body)))
        return replies.pop(0)

    monkeypatch.setattr(llm_extract, "_post_with_retries", fake_post)
    rec = run_task(AgentSpec("x", "openai_compat", "some/model"), TASKS["pilot-out-of-stock"])

    assert rec["stop"] == "done" and rec["questions"] == ["Budget?"]
    assert rec["score"]["as_asked"] and rec["score"]["asked_when_needed"]
    tool_msg = sent[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert json.loads(tool_msg["content"]) == {"reply": "Then don't buy anything, I'll wait."}
    assert sent[0]["tools"][0]["function"]["name"] == "search_products"


def test_openai_empty_reply_is_a_transport_error(monkeypatch):
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_BASE_URL", "https://proxy.test/v1")
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_API_KEY", "k")
    monkeypatch.setattr(llm_extract, "_post_with_retries", lambda *a, **k: {
        "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "", "reasoning_content": "call:get_product{}"}}]})
    rec = run_task(AgentSpec("x", "openai_compat", "m"), TASKS["pilot-vague"])
    assert rec["stop"] == "error" and rec["score"] is None


def test_openai_question_in_plain_text_goes_to_the_person(monkeypatch):
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_BASE_URL", "https://proxy.test/v1")
    monkeypatch.setattr(llm_extract, "OPENAI_COMPAT_API_KEY", "k")
    replies = [
        # a question in text, not through ask_user; reasoning does not count as a question
        {"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant",
            "content": "<mm:think>should I ask?</mm:think>Cheaper final sale, or pricier with returns?"}}]},
        {"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "<mm:think>ok?</mm:think>Understood, not buying."}}]},
    ]
    sent = []

    def fake_post(url, body, api_key=None):
        sent.append(json.loads(json.dumps(body)))
        return replies.pop(0)

    monkeypatch.setattr(llm_extract, "_post_with_retries", fake_post)
    rec = run_task(AgentSpec("x", "openai_compat", "some/model"), TASKS["pilot-out-of-stock"])

    assert rec["stop"] == "done" and rec["final_text"].endswith("Understood, not buying.")
    assert rec["questions"] == ["Cheaper final sale, or pricier with returns?"]
    assert sent[1]["messages"][-1] == {"role": "user",
                                       "content": "Then don't buy anything, I'll wait."}
