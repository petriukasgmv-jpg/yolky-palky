import os

GROQ_BROWSER_SEARCH_ERRORS = ("tool_use_failed", "output_parse_failed")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")


def chat_with_search(client, model, messages, max_tokens=1500):
    """Answer with live search, then use a searched fallback before plain AI."""
    tools = [{"type": "browser_search"}]
    try:
        completion = client.chat.completions.create(
            model=model, messages=messages, tools=tools, tool_choice="required",
            reasoning_effort="low", include_reasoning=False,
            max_completion_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""
    except Exception as error:
        print("=== GROQ PRIMARY SEARCH FAILED ===", repr(error), flush=True)
        if _is_tool_use_failed(error):
            try:
                completion = client.chat.completions.create(
                    model=model, messages=messages, tools=tools, tool_choice="auto",
                    reasoning_effort="low", include_reasoning=False,
                    max_completion_tokens=max_tokens,
                )
                return completion.choices[0].message.content or ""
            except Exception as retry_error:
                print("=== GROQ PRIMARY RETRY FAILED ===", repr(retry_error), flush=True)
        return _fallback(client, messages, max_tokens, tools)


def _fallback(client, messages, max_tokens, tools):
    """Try the lighter model with search; only then degrade to no-search mode."""
    try:
        print("=== GROQ SEARCH FALLBACK:", FALLBACK_MODEL, "===", flush=True)
        completion = client.chat.completions.create(
            model=FALLBACK_MODEL, messages=messages, tools=tools, tool_choice="auto",
            max_completion_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""
    except Exception as searched_error:
        print("=== GROQ SEARCH FALLBACK FAILED ===", repr(searched_error), flush=True)
        try:
            completion = client.chat.completions.create(
                model=FALLBACK_MODEL, messages=messages, max_tokens=max_tokens,
            )
            return completion.choices[0].message.content or ""
        except Exception as error:
            print("=== GROQ FALLBACK FAILED ===", repr(error), flush=True)
            raise


def _is_tool_use_failed(error):
    text = str(error)
    return "400" in text and any(code in text for code in GROQ_BROWSER_SEARCH_ERRORS)
