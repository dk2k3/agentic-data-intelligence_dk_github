from langchain_community.llms import Ollama
from app.agents.reasoning_schema import IntentType
import json


INTENT_RULES = {
    "aggregation": [
        "total", "sum", "average", "mean", "count",
        "how much", "how many"
    ],
    "ranking": [
        "top", "highest", "lowest", "most", "least", "best", "worst"
    ],
    "comparison": [
        "compare", "difference", "vs", "versus", "between"
    ],
    "trend": [
        "over time", "trend", "growth", "change", "yearly", "monthly"
    ],
    "distribution": [
        "distribution", "spread", "histogram", "frequency"
    ],
    "lookup": [
        "what is", "give me", "show", "find"
    ]
}


def classify_intent(question: str) -> IntentType:
    """
    Classifies the user's intent STRICTLY.
    If ambiguous → raises ValueError.
    """

    q = question.lower()

    matched_intents = []

    for intent, keywords in INTENT_RULES.items():
        for kw in keywords:
            if kw in q:
                matched_intents.append(intent)
                break

    # Remove duplicates
    matched_intents = list(set(matched_intents))

    # ----------------------------
    # STRICT DECISION LOGIC
    # ----------------------------

    if len(matched_intents) == 0:
        raise ValueError(
            "Unable to determine intent. Please rephrase your question."
        )

    if len(matched_intents) > 1:
        raise ValueError(
            f"Ambiguous intent detected: {matched_intents}. "
            "Please ask a more specific question."
        )

    return matched_intents[0]
