# Lessons (Friday)

Terse, high-signal rules learned during the build. Review at session start.

- Python must be 3.13 — ADK 2.2.0 does not install on 3.14 (the machine default).
- Local LLM at :8990 speaks the **Anthropic** protocol (`/v1/messages`), not OpenAI chat/completions. Use `LiteLlm(model="anthropic/<id>", api_base, api_key)`.
- ADK MCP + LiteLLM need extras: `google-adk[extensions]` + `mcp` + `litellm` + `sqlalchemy`.
- CallMissed search: `POST https://api.callmissed.com/v1/search`, `Authorization: Bearer cm_...`. Cite this doc source in code (provider-integration rule).
- Never commit `.env`; scrub `sk-`/`cm_`/Bearer from logs.
- Verify every phase by running it before marking the todo complete.
- Product is named **Friday** (env prefix `FRIDAY_`, runtime home `~/.friday`).
- CallMissed `mode`: `shorter`=serper/Google SERP, `detailed`/`auto`=exa neural. Occasional 503 = upstream outage; fallback path covers it.
