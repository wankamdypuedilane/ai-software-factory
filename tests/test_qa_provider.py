from ai_factory.providers import (
    QAProvider,
)
from ai_factory.qa_result import (
    QAResult,
)


class FakeQAProvider(QAProvider):
    def validate_qa(
        self,
        prompt: str,
    ) -> QAResult:
        return QAResult(
            summary="QA completed.",
            passed=True,
        )


def test_qa_provider_contract() -> None:
    provider: QAProvider = (
        FakeQAProvider()
    )

    result = provider.validate_qa(
        "Validate the application."
    )

    assert isinstance(
        result,
        QAResult,
    )

    assert result.summary == "QA completed."
    assert result.passed is True
