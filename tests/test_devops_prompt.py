from ai_factory.devops_prompt import (
    build_devops_prompt,
)


def test_build_devops_prompt_contains_delivery_context() -> None:
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
        "environment": {
            "target": "production",
        },
    }

    prompt = build_devops_prompt(
        context
    )

    assert "# DevOps Validation" in prompt
    assert "You are the DevOps Agent." in prompt

    assert "monolith" in prompt
    assert "src/app.py" in prompt
    assert "production" in prompt

    assert "CI/CD pipelines" in prompt
    assert "containerization" in prompt
    assert "infrastructure as code" in prompt
    assert "rollback strategy" in prompt

    assert (
        "Do not assume that the project is deployment-ready"
        in prompt
    )

    assert (
        "Production deployment still requires explicit human approval."
        in prompt
    )


def test_build_devops_prompt_serializes_empty_context() -> None:
    prompt = build_devops_prompt(
        {}
    )

    assert "# DevOps Validation" in prompt
    assert "## Project Context" in prompt
    assert "{}" in prompt
