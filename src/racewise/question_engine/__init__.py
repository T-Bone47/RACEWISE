"""RACEWISE general engineering question engine.

This package turns a free-text engineering question into a bounded,
evidence-driven investigation that composes the deterministic capabilities
that already exist. It does not replace the deterministic engine — it sits
*above* it and decides what to ask of it.

Layering (deliberate, and the reason the product cannot hallucinate):

    user language
        |
    [ compiler ]      language -> structured engineering question
        |             deterministic, closed vocabulary
    [ resolver ]      canonicalise drivers/races/scope; ask only when
        |             genuinely ambiguous
    [ decomposer ]    compound question -> sub-question DAG
        |
    [ planner ]       discover capabilities -> check data availability
        |             -> compose an evidence plan under a budget
    [ deterministic engine ]     <- the only thing that computes numbers
        |
    [ synthesizer ]   structured partial answer grounded in real results
        |
    [ verification ]  every claim traceable; nothing ungrounded survives

The language model, when configured, sits at exactly one boundary: turning
prose into the compiler's schema. It never sees or emits numbers, never picks
tools directly, and is never required — with no provider configured the
deterministic compiler handles the supported vocabulary and the system stays
honest.
"""
from racewise.question_engine.capabilities import (
    Capability,
    all_capabilities,
    capability,
    capability_matrix,
    registry_version,
)
from racewise.question_engine.compiler import (
    CompiledQuestion,
    compile_question,
    needs_clarification,
)
from racewise.question_engine.decomposer import SubQuestion, decompose
from racewise.question_engine.planner import (
    InvestigationPlan,
    build_plan,
    plan_version,
)
from racewise.question_engine.synthesizer import (
    Answer,
    answer_status,
    synthesize,
)
from racewise.question_engine.verification import (
    VerificationReport,
    verify_answer,
)

__all__ = [
    "Answer",
    "Capability",
    "CompiledQuestion",
    "InvestigationPlan",
    "SubQuestion",
    "VerificationReport",
    "all_capabilities",
    "answer_status",
    "build_plan",
    "capability",
    "capability_matrix",
    "compile_question",
    "decompose",
    "needs_clarification",
    "registry_version",
    "plan_version",
    "synthesize",
    "verify_answer",
]