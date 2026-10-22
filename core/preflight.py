"""What can be checked before a run, in words the user can act on."""
LOOPBACK = ("localhost", "127.0.0.1", "::1")


def ollama_problems(asked: list[tuple[str, str]], installed: dict[str, list[str] | None]) -> list[str]:
    """asked: (address, model) of the Ollama nodes of the graph. installed: the models each address has, None when it does not answer."""
    problems = []
    for url, model in dict.fromkeys(asked):
        have = installed.get(url)
        if have is None:
            problems.append(f"Ollama does not answer at {url}. Start it, then run again.")
        elif model not in have and f"{model}:latest" not in have:
            problems.append(f"Ollama does not have the model '{model}'. Install it with: ollama pull {model}")
    return list(dict.fromkeys(problems))
