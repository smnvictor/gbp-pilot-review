from typing import Any

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.integrations.claude.adapter import LLMRequest, LLMResponse

TOOL_NAME = "submit_review_response"
TOOL_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Submit the generated reply to a Google Business review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "integer",
                "enum": [0, 1],
                "description": "1 = generated content, 0 = refusal with reason in details",
            },
            "content": {
                "type": "string",
                "description": "The reply text. Empty string when status=0.",
            },
            "details": {
                "type": "string",
                "description": "Refusal nomenclature code if status=0. Empty string if status=1.",
            },
        },
        "required": ["status", "content", "details"],
    },
}


class ClaudeClient:
    """Anthropic SDK-backed LLM provider."""

    def __init__(self, sdk: AsyncAnthropic | None = None) -> None:
        settings = get_settings()
        self._sdk = sdk or AsyncAnthropic(api_key=settings.claude_api_key.get_secret_value())

    async def generate(self, request: LLMRequest) -> LLMResponse:
        message = await self._sdk.messages.create(  # type: ignore[call-overload]
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=[
                {
                    "type": "text",
                    "text": request.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": request.user_prompt}],
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": TOOL_NAME},
        )

        usage_in = getattr(message.usage, "input_tokens", 0) or 0
        usage_out = getattr(message.usage, "output_tokens", 0) or 0

        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == TOOL_NAME:
                payload = block.input or {}
                return LLMResponse(
                    status=1 if int(payload.get("status", 0)) == 1 else 0,
                    content=str(payload.get("content", "")),
                    details=payload.get("details", ""),
                    tokens_input=usage_in,
                    tokens_output=usage_out,
                    model=request.model,
                )

        # Fallback: model returned no tool_use block — treat as generation_error
        return LLMResponse(
            status=0,
            content="",
            details="generation_error",
            tokens_input=usage_in,
            tokens_output=usage_out,
            model=request.model,
        )
