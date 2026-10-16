from ai_factory.state_digest import digest_state


STATE = {
    "iteration": 4,
    "agents": {
        "product": {"status": "APPROVED", "last_result": {"summary": "Cadrage", "question_details": ["x" * 5000]}},
        "developer": {
            "status": "FAILED",
            "replan_budget_resets": [{"at": "t"}] * 20,
            "auto_diagnoses": [{"cause": "x" * 3000}],
            "last_result": {
                "summary": "Plan",
                "owner_summary": {"will_do": ["x" * 3000]},
                "failed_task_id": "T-2",
                "implementation_results": [{"task_id": "T-1", "summary": "s" * 2000, "files": ["a.ts"], "tests": ["npm test"]}],
                "test_results": [
                    {"command": "ok", "returncode": 0, "passed": True, "stdout": "y" * 9000},
                    {"command": "ko", "returncode": 1, "passed": False, "stdout": "z" * 9000, "stderr": ""},
                ],
            },
        },
    },
}


def test_the_working_agent_keeps_what_it_needs_to_continue() -> None:
    developer = digest_state(STATE, "developer")["agents"]["developer"]

    assert developer["status"] == "FAILED"
    assert "replan_budget_resets" not in developer and "auto_diagnoses" not in developer
    result = developer["last_result"]
    assert result["failed_task_id"] == "T-2"
    assert "owner_summary" not in result
    assert result["implementation_results"][0]["files"] == ["a.ts"]
    assert len(result["implementation_results"][0]["summary"]) < 400
    passed, failed = result["test_results"]
    assert "stdout" not in passed
    assert len(failed["stdout"]) < 2100


def test_other_agents_are_reduced_to_status_and_summary() -> None:
    product = digest_state(STATE, "developer")["agents"]["product"]

    assert product == {"status": "APPROVED", "summary": "Cadrage"}


def test_the_state_itself_is_left_untouched() -> None:
    digest_state(STATE, "developer")

    assert len(STATE["agents"]["developer"]["replan_budget_resets"]) == 20
    assert "owner_summary" in STATE["agents"]["developer"]["last_result"]
