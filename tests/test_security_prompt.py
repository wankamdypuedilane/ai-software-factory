from ai_factory.security_prompt import (
    build_security_prompt,
)


def test_build_security_prompt_contains_security_context() -> None:
    context = {
        "project": {
            "name": "Test Project",
        },
        "architecture": {
            "style": "monolith",
        },
        "developer": {
            "implemented_files": [
                "src/auth.py",
            ],
        },
        "qa": {
            "qa_passed": True,
            "qa_defects": [],
        },
        "security_requirements": [
            "Passwords must be hashed.",
        ],
    }

    prompt = build_security_prompt(
        context
    )

    assert "# Security Validation" in prompt
    assert "You are the Security Agent." in prompt

    assert "monolith" in prompt
    assert "src/auth.py" in prompt
    assert "Passwords must be hashed." in prompt

    assert "authentication" in prompt
    assert "authorization" in prompt
    assert "secrets management" in prompt

    assert (
        "Do not assume that the implementation is secure"
        in prompt
    )

    assert "Critical" in prompt
    assert "High" in prompt
    assert "Medium" in prompt
    assert "Low" in prompt
    assert "Informational" in prompt


def test_build_security_prompt_serializes_empty_context() -> None:
    prompt = build_security_prompt(
        {}
    )

    assert "# Security Validation" in prompt
    assert "## Project Context" in prompt
    assert "{}" in prompt
