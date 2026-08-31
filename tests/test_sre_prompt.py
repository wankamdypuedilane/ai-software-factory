from ai_factory.sre_prompt import (
    build_sre_prompt,
)


def test_build_sre_prompt_contains_operational_context() -> None:
    context = {
        "project": {
            "name": "Test Project",
        },
        "architecture": {
            "style": "monolith",
        },
        "developer": {
            "implemented_files": [
                "src/app.py",
            ],
        },
        "qa": {
            "qa_passed": True,
        },
        "security": {
            "security_passed": True,
        },
        "devops": {
            "devops_passed": True,
            "deployment_ready": True,
        },
    }

    prompt = build_sre_prompt(
        context
    )

    assert "# SRE Validation" in prompt
    assert "You are the SRE Agent." in prompt

    assert "monolith" in prompt
    assert "src/app.py" in prompt
    assert '"deployment_ready": true' in prompt

    assert "health checks" in prompt
    assert "application logs" in prompt
    assert "metrics" in prompt
    assert "distributed tracing" in prompt
    assert "alerting" in prompt
    assert "runbooks" in prompt
    assert "capacity" in prompt
    assert "resilience" in prompt

    assert (
        "Do not assume that the system is operationally ready"
        in prompt
    )

    assert (
        "Do not invent reliability targets."
        in prompt
    )


def test_build_sre_prompt_serializes_empty_context() -> None:
    prompt = build_sre_prompt(
        {}
    )

    assert "# SRE Validation" in prompt
    assert "## Project Context" in prompt
    assert "{}" in prompt
