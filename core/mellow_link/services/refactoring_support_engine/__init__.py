__all__ = [
    "RefactoringSupportEngineFacade",
    "ExplanationPresenter",
    "ResultQuestionAnsweringService",
    "load_engine_policy_bundle",
]


def __getattr__(name: str):
    if name == "RefactoringSupportEngineFacade":
        from .facade import RefactoringSupportEngineFacade as value
    elif name == "ExplanationPresenter":
        from .explanation_presenter import ExplanationPresenter as value
    elif name == "ResultQuestionAnsweringService":
        from .result_question_answering import ResultQuestionAnsweringService as value
    elif name == "load_engine_policy_bundle":
        from .policies import load_engine_policy_bundle as value
    else:
        raise AttributeError(name)

    globals()[name] = value
    return value
