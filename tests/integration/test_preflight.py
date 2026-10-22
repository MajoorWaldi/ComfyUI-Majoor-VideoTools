from majoor_videotools.core.preflight import ollama_problems

URL = "http://127.0.0.1:11434"


def test_a_model_that_is_there_is_not_a_problem():
    assert ollama_problems([(URL, "gemma4"), (URL, "qwen3.8:latest")], {URL: ["gemma4:latest", "qwen3.8:latest"]}) == []


def test_a_missing_model_says_how_to_install_it():
    assert ollama_problems([(URL, "qwen3.8:latest")], {URL: ["gemma4:latest"]}) == ["Ollama does not have the model 'qwen3.8:latest'. Install it with: ollama pull qwen3.8:latest"]


def test_an_ollama_that_does_not_answer_is_said_once():
    assert ollama_problems([(URL, "a"), (URL, "b")], {URL: None}) == [f"Ollama does not answer at {URL}. Start it, then run again."]
