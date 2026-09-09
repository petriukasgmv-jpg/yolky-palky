import os

GROQ_BROWSER_SEARCH_ERRORS = ("tool_use_failed", "output_parse_failed")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")


def chat_with_search(client, model, messages, max_tokens=1500):
    """Call Groq chat with browser_search available.

    Tries with tool_choice="required" first (guarantees live web data).
    If the model refuses to call the tool (tool_use_failed /
    output_parse_failed), retries with tool_choice="auto" so the model
    can still decide to search but will not be forced.

    If the primary model fails for any other reason (for example the
    daily token budget is exhausted), falls back to a lighter model so
    users still get an answer instead of an error.

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
        if _is_tool_use_failed(e):
            # Model refused the forced tool: retry in "auto" mode. The model
            # may still run browser_search itself and return web results.
            try:
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
            except Exception as retry_error:
                print("=== GROQ PRIMARY MODEL FAILED ON RETRY ===", flush=True)
                print(repr(retry_error), flush=True)
        else:
            print("=== GROQ PRIMARY MODEL FAILED ===", flush=True)
            print(repr(e), flush=True)
        return _fallback(client, messages, max_tokens)


def _fallback(client, messages, max_tokens):
    """Serve the request with a lighter model (e.g. when the daily token
    budget of the main model is exhausted). No browser tools."""
    try:
        print("=== GROQ FALLBACK MODEL:", FALLBACK_MODEL, "===", flush=True)
        completion = client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=messages,
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""
    except Exception as e:
        print("=== GROQ FALLBACK FAILED ===", flush=True)
        print(repr(e), flush=True)
        raise


def _is_tool_use_failed(error):
    text = str(error)
    return "400" in text and any(code in text for code in GROQ_BROWSER_SEARCH_ERRORS)