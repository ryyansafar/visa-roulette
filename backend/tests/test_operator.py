import pytest
from fastapi.testclient import TestClient

from visa_roulette import flow_api, operator as op
from visa_roulette.api import create_app

client = TestClient(create_app())


def boom(*_a, **_k):
    raise ConnectionError("ollama is off")


def test_facts_come_from_the_rules_not_the_caller():
    facts = op.facts("IND", "THA", [])
    assert facts["destination"] == "Thailand" and facts["status"] and facts["source_url"]
    assert facts["papers"] and all(isinstance(p, str) for p in facts["papers"])


def test_the_prompt_carries_the_facts_and_the_question_but_the_question_is_not_a_system_message():
    msgs = op.build_messages("Do I need cash?", op.facts("IND", "THA", []))
    assert msgs[0]["role"] == "system" and "Thailand" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "Do I need cash?"}
    assert "Do I need cash?" not in msgs[0]["content"]


def test_a_grounded_answer_passes_and_an_invented_number_fails():
    facts = op.facts("IND", "THA", [])
    assert op.grounded("You are fine to go. Bring your passport.", facts)
    assert not op.grounded("The visa fee is 9999 dollars.", facts)
    assert not op.grounded("See https://evil.example/pay", facts)
    assert not op.grounded("x" * 500, facts)
    assert not op.grounded("", facts)


def test_ask_uses_the_model_answer_when_it_is_grounded():
    out = op.ask("What do I bring?", "IND", "THA", [], chat=lambda m: "Bring your passport and a return ticket.")
    assert out["source"] == "ai" and "passport" in out["text"]


def test_ask_falls_back_to_the_rules_when_the_model_is_off():
    out = op.ask("What do I bring?", "IND", "THA", [], chat=boom)
    assert out["source"] == "rules" and "Thailand" in out["text"]


def test_ask_falls_back_when_the_model_invents_a_number():
    out = op.ask("fee?", "IND", "THA", [], chat=lambda m: "It costs 4321 rupees.")
    assert out["source"] == "rules"


def test_rude_questions_never_reach_the_model():
    calls = []
    out = op.ask("you fucking idiot", "IND", "THA", [], chat=lambda m: calls.append(m) or "hi")
    assert not calls and out["source"] == "rules"


def test_long_questions_are_cut_before_prompting():
    seen = []
    op.ask("a" * 5000, "IND", "THA", [], chat=lambda m: seen.append(m) or "ok")
    assert len(seen[0][-1]["content"]) <= op.MAX_QUESTION


def test_the_ask_endpoint_answers_even_with_the_model_off(monkeypatch):
    monkeypatch.setattr(op, "ollama_chat", boom)
    out = client.post("/api/operator/ask", json={"question": "what do I need?", "nationality": "IND", "destination": "THA"})
    assert out.status_code == 200 and out.json()["source"] == "rules" and out.json()["text"]


def test_the_ask_endpoint_rejects_unknown_countries_and_empty_questions():
    assert client.post("/api/operator/ask", json={"question": "hi", "nationality": "IND", "destination": "ZZZ"}).status_code == 422
    assert client.post("/api/operator/ask", json={"question": "", "nationality": "IND", "destination": "THA"}).status_code == 422
