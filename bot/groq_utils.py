GROQ_BROWSER_SEARCH_ERRORS = ("tool_use_failed", "output_parse_failed")


def chat_with_search(client, model, messages, max_tokens=1500):
    """Call Groq chat with browser_search available.

    Tries with tool_choice="required" first (guarantees live web data).
    If the model refuses to call the tool (tool_use_failed /
    output_parse_failed), retries with tool_choice="auto" so the model
    can still decide to search but will not be forced.

    Returns the final message content (str) or raises on fatal errors.
    """
    tools = [{"type": "browser_search"}]

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="required",
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""
    except Exception as e:
        if not _is_tool_use_failed(e):
            raise
        # Model refused the forced tool: retry in "auto" mode. The model
        # may still run browser_search itself and return web results.
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""


def _is_tool_use_failed(error):
    text = str(error)
    return "400" in text and any(code in text for code in GROQ_BROWSER_SEARCH_ERRORS)