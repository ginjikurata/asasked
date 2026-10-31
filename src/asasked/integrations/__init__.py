"""Страж в популярных библиотеках агентов: проверка встаёт перед инструментом
оплаты, и агент не может его обойти.

    claude_agent   — Claude Agent SDK, крючок PreToolUse
    openai_agents  — OpenAI Agents SDK, tool_input_guardrail
    langchain      — LangChain 1.x, middleware вокруг вызова инструмента

Везде одно и то же: cart(аргументы инструмента) → корзина словарями (как в
Guard.check). Расхождение — оплата не вызывается, агент получает вопрос для
человека (guard.NOT_PAID). Ответ человека передаёт ваш код: guard.answer(...).
"""
