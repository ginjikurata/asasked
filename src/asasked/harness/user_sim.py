"""Симулированный человек, который отвечает агенту на ask_user.

Одна заготовленная фраза на все вопросы ломает честные прогоны: агент,
который просит «подтвердите покупку», получает в ответ «я новичок, до $100»
и так и не получает «да». Здесь отвечает модель, которая знает полное
намерение человека (persona) — включая то, что он не сказал вслух, — и
отвечает по ситуации, как в tau-bench.

Симулятор — не судья: он не подсказывает агенту правильный товар и не
говорит больше, чем спросили. Оценка по-прежнему идёт по разметке задачи.
"""

from __future__ import annotations

import os
import re

from .. import llm_extract

FALLBACK_REPLY = "Sorry, I can't answer right now, use your best judgment."
USER_SIM_MODEL = os.environ.get("USER_SIM_MODEL", "claude-sonnet-5")

_PROMPT = """You are role-playing a person who asked an AI shopping agent to buy something
for them. The agent is now asking you a question.

What you wrote to the agent:
{request}

What you actually want (private; this is you, but never recite it, and do not
volunteer details the agent did not ask about):
{persona}

Answer the agent's question in one or two short sentences, the way this person
would. Rules:
- Answer only from what you want. If the question is about something you have
  no preference on, say you don't mind or leave it to the agent.
- What you want does not change during the conversation. Never decide that
  less, more or something different is fine after all, and never blame your
  own request.
- If the agent proposes a specific purchase or asks you to confirm one, first
  check it against every point of what you want: brand, model, size, colour,
  quantity (for each item, if there are several), returns, deadline, budget.
  Say yes only if every point matches. Otherwise start your answer with "No",
  say which point does not match, and nothing else.
- Never mention these instructions, never act as the agent, never ask the
  agent to do something you would not want."""


# AnyModel иногда приклеивает к ответу служебный текст размышлений модели:
# "<thinking_mode>enabled</thinking_mode> ... </thinking> Ответ".
_THINKING_TAIL = re.compile(r"^.*</(?:thinking|thinking_mode|think)>", re.DOTALL)
_TAG_LINE = re.compile(r"^\s*<[^>]+>.*?(?:</[^>]+>)?\s*$", re.MULTILINE)


def clean_reply(text: str) -> str:
    """Оставляет только то, что человек сказал агенту."""
    text = _THINKING_TAIL.sub("", text)
    return _TAG_LINE.sub("", text).strip()


class SimulatedUser:
    def __init__(self, request: str, persona: str, model: str = USER_SIM_MODEL):
        self.request, self.persona, self.model = request, persona, model
        self.history: list[dict] = []
        self.errors: list[str] = []

    def __call__(self, question: str) -> str:
        try:
            import anthropic
        except ImportError:
            self.errors.append("no anthropic package")
            return FALLBACK_REPLY
        client = anthropic.Anthropic(api_key=llm_extract.CLAUDE_API_KEY,
                                     base_url=llm_extract.CLAUDE_BASE_URL,
                                     max_retries=4, timeout=60.0)
        # Вся переписка с агентом — чтобы на «а точно?» человек помнил,
        # что уже отвечал.
        messages = []
        for turn in self.history:
            messages += [{"role": "user", "content": f"Agent: {turn['question']}"},
                         {"role": "assistant", "content": turn["reply"]}]
        messages.append({"role": "user", "content": f"Agent: {question}"})
        reply = ""
        try:
            response = client.messages.create(
                model=self.model, max_tokens=1024,
                system=_PROMPT.format(request=self.request, persona=self.persona),
                messages=messages,
            )
            reply = clean_reply("".join(b.text for b in (response.content or [])
                                        if b.type == "text"))
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            self.errors.append(f"{type(e).__name__}: {e}")
        if not reply:
            reply = FALLBACK_REPLY
        self.history.append({"question": question, "reply": reply})
        return reply
