"""T3.3 acceptance: digit-guard rejects invented numbers; offline mode works."""

from types import SimpleNamespace

from engine.rules.base import Finding
from report.ai_explain import (
    AiExplainer,
    allowed_numbers,
    digit_violations,
    finding_key,
)

FINDING = Finding(
    rule_id="R-Q1",
    severity="CRITICAL",
    title="One query consumes a large share of total database time",
    evidence={"calls": 4133, "total_ms": 6300.9, "pct_of_db_time": 69.1, "mean_ms": 1.52},
    affected_object="SELECT ... FROM orders WHERE customer_id = ?",
    suggested_action="Template fallback text: investigate the execution plan first.",
    engine="postgres",
    category="queries",
)


class FakeClient:
    """Returns queued responses; records the prompts it was asked."""

    def __init__(self, *texts: str):
        self._texts = list(texts)
        self.prompts: list[str] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        text = self._texts.pop(0)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
        )


# --- digit guard mechanics ---------------------------------------------------


def test_allowed_numbers_include_formatting_variants():
    strings, floats = allowed_numbers('{"calls": 4133, "total_ms": 6300.9}')
    assert not digit_violations(
        "It ran 4,133 times for 6300.9 ms total (6300 ms).", strings, floats
    )


def test_invented_numbers_are_violations():
    strings, floats = allowed_numbers('{"calls": 4133}')
    assert digit_violations("This will make queries 50% faster.", strings, floats) == ["50"]
    assert digit_violations("Roughly 4000 calls.", strings, floats) == ["4000"]


# --- explainer behavior ------------------------------------------------------


def test_grounded_answer_accepted_and_cached(tmp_path):
    good = "The query ran 4133 times, consuming 69.1% of database time. Next: check its plan."
    client = FakeClient(good)
    ex = AiExplainer(model="test-model", cache_dir=tmp_path, client=client)
    assert ex.explain(FINDING) == good
    # second call hits the cache, not the API
    assert ex.explain(FINDING) == good
    assert len(client.prompts) == 1


def test_invented_number_rejected_then_retry_succeeds(tmp_path):
    bad = "This query will get 80% faster if you add an index."
    good = "The query ran 4133 times. Next: add the suggested index in staging."
    client = FakeClient(bad, good)
    ex = AiExplainer(model="test-model", cache_dir=tmp_path, client=client)
    assert ex.explain(FINDING) == good
    assert len(client.prompts) == 2
    assert "previous draft contained a number" in client.prompts[1]


def test_invented_number_twice_falls_back_to_template(tmp_path):
    client = FakeClient("80% faster!", "Still 99% faster!!")
    ex = AiExplainer(model="test-model", cache_dir=tmp_path, client=client)
    assert ex.explain(FINDING) == FINDING.suggested_action
    # a rejected answer must never be cached
    assert not list(tmp_path.iterdir())


def test_api_error_falls_back_to_template(tmp_path):
    class ExplodingClient:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("api down")

    ex = AiExplainer(model="test-model", cache_dir=tmp_path, client=ExplodingClient())
    assert ex.explain(FINDING) == FINDING.suggested_action


def test_offline_without_api_key_uses_template(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ex = AiExplainer(model="test-model", cache_dir=tmp_path)
    assert ex.explain(FINDING) == FINDING.suggested_action


def test_prompt_contains_only_evidence_never_snapshots(tmp_path):
    client = FakeClient("The query ran 4133 times. Next step: check the plan.")
    ex = AiExplainer(model="test-model", cache_dir=tmp_path, client=client)
    ex.explain(FINDING)
    prompt = client.prompts[0]
    assert "4133" in prompt and "69.1" in prompt
    assert "SELECT" in prompt  # normalized statement is allowed (no literals in it)


def test_finding_key_is_stable():
    assert finding_key(FINDING) == finding_key(FINDING.model_copy())
    other = FINDING.model_copy(update={"affected_object": "different"})
    assert finding_key(FINDING) != finding_key(other)
