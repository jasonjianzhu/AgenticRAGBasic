from __future__ import annotations

import respx
from httpx import Response

from app.llm.minimax import MiniMaxClient


@respx.mock
def test_minimax_client_rewrite_query_uses_anthropic_compatible_api() -> None:
    route = respx.post("https://api.minimaxi.com/anthropic/v1/messages").mock(
        return_value=Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": '{"rewritten_query":"E101 troubleshooting","expanded_queries":["E101 alarm handling"],"language":"en","document_type":"manual"}',
                    }
                ]
            },
        )
    )

    client = MiniMaxClient(
        base_url="https://api.minimaxi.com/anthropic",
        api_key="test-key",
        model="MiniMax-M2.7",
    )

    result = client.rewrite_query("E101 怎么处理")

    assert route.called
    assert result.rewritten_query == "E101 troubleshooting"
    assert result.expanded_queries == ["E101 alarm handling"]


@respx.mock
def test_minimax_client_generate_answer_returns_text() -> None:
    route = respx.post("https://api.minimaxi.com/anthropic/v1/messages").mock(
        return_value=Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": "Answer: Check cooling fan status. Citation: pcs.pdf page 5.",
                    }
                ]
            },
        )
    )

    client = MiniMaxClient(
        base_url="https://api.minimaxi.com/anthropic",
        api_key="test-key",
        model="MiniMax-M2.7",
    )

    result = client.generate_answer(
        query="How to handle E101 alarm?",
        context_blocks=["Alarm code E101 indicates battery overheat. Check cooling fan status."],
    )

    assert route.called
    assert "Check cooling fan status" in result
