"""The guard in popular agent libraries: the check stands in front of the
payment tool, and the agent cannot go around it.

    claude_agent   - Claude Agent SDK, a PreToolUse hook
    openai_agents  - OpenAI Agents SDK, a tool_input_guardrail
    langchain      - LangChain 1.x, middleware around the tool call

The same everywhere: cart(tool arguments) -> the cart as dicts (as in
Guard.check). On a mismatch payment is not called and the agent gets a
question for the person (guard.NOT_PAID). The person's answer is passed on by
your code: guard.answer(...).
"""
