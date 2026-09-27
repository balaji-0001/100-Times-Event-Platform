"""LangChain + LangGraph layer over the two existing agents.

- `tools.py`  — LangChain tools that call the same route functions the admin
                console's buttons call (Agent 1 discovery, Agent 2 outreach
                drafting, follow-up processing), with the routes' own input
                validation.
- `llm.py`    — a LangChain Runnable for structured LLM calls that goes
                through the provider-neutral `ai_client.py` (validation +
                bounded retry), for any new step that needs one.
- `graph.py`  — the LangGraph workflow that sequences Agent 1 -> Agent 2 ->
                follow-ups with typed state, conditional routing, retry on
                transient errors, and an `AgentRun(agent_type="workflow")`
                audit row.

Nothing in this package changes how the agents themselves work, what they
store, or the approval gate on outgoing email.
"""
