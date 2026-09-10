from tourism_agent.observability.langfuse import LangfuseObservability, NoOpObservability


def build_observability(settings):
    return LangfuseObservability(
        enabled=settings.langfuse_enabled,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
        sample_rate=settings.langfuse_sample_rate,
    )


__all__ = ["LangfuseObservability", "NoOpObservability", "build_observability"]
