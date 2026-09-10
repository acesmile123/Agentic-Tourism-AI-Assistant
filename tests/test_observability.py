from tourism_agent.observability.langfuse import LangfuseObservability, NoOpObservability
from tourism_agent.services.generation import GeminiGenerationService


def test_observability_is_noop_without_credentials():
    observer = LangfuseObservability(
        enabled=True,
        public_key="",
        secret_key="",
        base_url="https://cloud.langfuse.com",
        environment="test",
    )

    assert observer.enabled is False
    with observer.span("test", input={"query": "hello"}) as span:
        span.update(output="ok")


def test_noop_observer_does_not_swallow_application_errors():
    try:
        with NoOpObservability().span("test"):
            raise RuntimeError("application error")
    except RuntimeError as exc:
        assert str(exc) == "application error"
    else:
        raise AssertionError("application exception was swallowed")


def test_gemini_usage_metadata_is_mapped_to_langfuse_fields():
    class Usage:
        prompt_token_count = 10
        candidates_token_count = 5
        total_token_count = 15
        cached_content_token_count = 2
        thoughts_token_count = 1

    class Response:
        usage_metadata = Usage()

    assert GeminiGenerationService._usage(Response()) == {
        "input": 10,
        "output": 5,
        "total": 15,
        "cache_read_input_tokens": 2,
        "reasoning": 1,
    }
