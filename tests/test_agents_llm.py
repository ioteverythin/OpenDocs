#!/usr/bin/env python3
"""Integration test — agentic pipeline with REAL LLM calls (OpenAI).

Runs the full Planner → Executor → Critic loop against a real GitHub repo
with use_llm=True so that GPT calls fire in the Planner, Critic, and
any activated specialized agents.

Usage:
    set OPENAI_API_KEY=sk-...
    python test_agents_llm.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback

# ── ensure src/ is on the path ──────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from opendocs.agents.base import RepoProfile, RepoSignal
from opendocs.agents.orchestrator import AgentOrchestrator
from opendocs.agents.privacy import PrivacyMode
from opendocs.core.knowledge_graph import (
    KnowledgeGraph, Entity, EntityType, Relation, RelationType,
)


# ---------------------------------------------------------------------------
# Helper — build a synthetic but realistic RepoProfile + KnowledgeGraph
# ---------------------------------------------------------------------------

def build_fastapi_profile() -> tuple[RepoProfile, KnowledgeGraph]:
    """Simulated profile for tiangolo/fastapi (microservices + ML adjacent)."""
    kg = KnowledgeGraph()

    # Add representative entities
    entities_data = [
        ("FastAPI", EntityType.FRAMEWORK),
        ("Starlette", EntityType.FRAMEWORK),
        ("Pydantic", EntityType.TECHNOLOGY),
        ("Uvicorn", EntityType.TECHNOLOGY),
        ("OpenAPI", EntityType.TECHNOLOGY),
        ("SQLAlchemy", EntityType.TECHNOLOGY),
        ("Docker", EntityType.TECHNOLOGY),
        ("pytest", EntityType.TECHNOLOGY),
        ("OAuth2", EntityType.PROTOCOL),
        ("WebSocket", EntityType.PROTOCOL),
    ]
    for name, etype in entities_data:
        kg.add_entity(Entity(
            id=name.lower().replace(" ", "_"),
            name=name,
            entity_type=etype,
            properties={"source": "readme"},
        ))

    # Add a few relations
    kg.add_relation(Relation(source_id="fastapi", target_id="starlette", relation_type=RelationType.DEPENDS_ON))
    kg.add_relation(Relation(source_id="fastapi", target_id="pydantic", relation_type=RelationType.DEPENDS_ON))
    kg.add_relation(Relation(source_id="fastapi", target_id="uvicorn", relation_type=RelationType.RUNS_ON))
    kg.add_relation(Relation(source_id="fastapi", target_id="docker", relation_type=RelationType.RUNS_ON))

    profile = RepoProfile(
        repo_name="tiangolo/fastapi",
        repo_url="https://github.com/tiangolo/fastapi",
        description=(
            "FastAPI framework, high performance, easy to learn, fast to code, "
            "ready for production. Based on Python 3.8+ type hints. "
            "Uses Starlette for the web parts and Pydantic for the data parts."
        ),
        primary_language="Python",
        languages=["Python", "Shell", "Dockerfile"],
        file_tree=[
            "fastapi/__init__.py",
            "fastapi/applications.py",
            "fastapi/routing.py",
            "fastapi/dependencies/",
            "fastapi/security/oauth2.py",
            "docker-compose.yml",
            "Dockerfile",
            "requirements.txt",
            "tests/",
        ],
        signals=[
            RepoSignal(signal_type="docker-compose", file_path="docker-compose.yml", confidence=0.8),
            RepoSignal(signal_type="Dockerfile", file_path="Dockerfile", confidence=0.9),
            RepoSignal(signal_type="oauth2", file_path="fastapi/security/oauth2.py", confidence=0.7),
        ],
    )

    return profile, kg


def build_transformers_profile() -> tuple[RepoProfile, KnowledgeGraph]:
    """Simulated profile for huggingface/transformers (heavy ML)."""
    kg = KnowledgeGraph()

    entities_data = [
        ("Transformers", EntityType.TECHNOLOGY),
        ("PyTorch", EntityType.FRAMEWORK),
        ("TensorFlow", EntityType.FRAMEWORK),
        ("BERT", EntityType.COMPONENT),
        ("GPT-2", EntityType.COMPONENT),
        ("Tokenizer", EntityType.COMPONENT),
        ("Pipeline", EntityType.COMPONENT),
        ("Trainer", EntityType.COMPONENT),
        ("HuggingFace Hub", EntityType.PLATFORM),
        ("ONNX", EntityType.TECHNOLOGY),
        ("safetensors", EntityType.TECHNOLOGY),
    ]
    for name, etype in entities_data:
        kg.add_entity(Entity(
            id=name.lower().replace(" ", "_").replace("-", "_"),
            name=name,
            entity_type=etype,
            properties={"source": "readme"},
        ))

    kg.add_relation(Relation(source_id="transformers", target_id="pytorch", relation_type=RelationType.DEPENDS_ON))
    kg.add_relation(Relation(source_id="transformers", target_id="tensorflow", relation_type=RelationType.DEPENDS_ON))
    kg.add_relation(Relation(source_id="pipeline", target_id="tokenizer", relation_type=RelationType.USES))
    kg.add_relation(Relation(source_id="trainer", target_id="pytorch", relation_type=RelationType.DEPENDS_ON))

    profile = RepoProfile(
        repo_name="huggingface/transformers",
        repo_url="https://github.com/huggingface/transformers",
        description=(
            "State-of-the-art Machine Learning for PyTorch, TensorFlow, and JAX. "
            "Thousands of pretrained models for NLP, computer vision, audio, "
            "and multimodal tasks."
        ),
        primary_language="Python",
        languages=["Python", "Jupyter Notebook", "Shell"],
        file_tree=[
            "src/transformers/models/bert/",
            "src/transformers/models/gpt2/",
            "src/transformers/pipelines/",
            "src/transformers/trainer.py",
            "src/transformers/tokenization_utils.py",
            "model_card_template.md",
            "setup.py",
            "requirements.txt",
            "docker/Dockerfile",
            "tests/",
        ],
        signals=[
            RepoSignal(signal_type="pytorch", file_path="requirements.txt", confidence=0.95),
            RepoSignal(signal_type="tensorflow", file_path="requirements.txt", confidence=0.90),
            RepoSignal(signal_type="huggingface", file_path="setup.py", confidence=0.95),
            RepoSignal(signal_type="model_card", file_path="model_card_template.md", confidence=0.85),
            RepoSignal(signal_type="Dockerfile", file_path="docker/Dockerfile", confidence=0.4),
        ],
    )

    return profile, kg


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

async def run_single_repo(
    label: str,
    profile: RepoProfile,
    kg: KnowledgeGraph,
) -> dict:
    """Run the orchestrator with use_llm=True against one repo profile."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}\n")

    orch = AgentOrchestrator(
        model="gpt-4o-mini",
        privacy_mode=PrivacyMode.STANDARD,
        max_retries=1,
    )

    t0 = time.perf_counter()
    result = await orch.run(
        repo_profile=profile,
        knowledge_graph=kg,
        use_llm=True,
    )
    elapsed = time.perf_counter() - t0

    summary = result.summary()

    print(f"\n--- Summary for {label} ---")
    print(json.dumps(summary, indent=2, default=str))
    print(f"Wall time: {elapsed:.1f}s")
    print(f"Approved: {result.approved}")
    print(f"Iterations: {result.iterations}")
    print(f"Artifacts: {list(result.enhanced_artifacts.keys())}")

    # Print a snippet of each artifact
    for key, val in result.enhanced_artifacts.items():
        print(f"\n  >> artifact: {key}")
        if isinstance(val, str):
            preview = val[:400].replace("\n", "\n    ")
            print(f"    {preview}{'...' if len(val) > 400 else ''}")
        elif isinstance(val, dict):
            print(f"    (dict with {len(val)} keys)")
        elif isinstance(val, list):
            print(f"    (list with {len(val)} items)")
        else:
            print(f"    {str(val)[:200]}")

    # Check for LLM metadata
    for sr in result.step_results:
        meta = sr.metadata or {}
        if meta.get("llm_used") or meta.get("llm_reviewed"):
            print(f"\n  ✓ LLM was used in step (agent_role={sr.agent_role})")
            for k, v in meta.items():
                if "llm" in k.lower():
                    print(f"      {k}: {v}")

    if result.critic_result:
        critic_meta = result.critic_result.metadata or {}
        if critic_meta.get("llm_reviewed"):
            print(f"\n  ✓ LLM review included in Critic verdict")
            llm_review = result.critic_result.artifacts.get("verdict", {})
            if isinstance(llm_review, dict) and "llm_review" in llm_review:
                rev = str(llm_review["llm_review"])[:500]
                print(f"    LLM Review snippet: {rev}...")

    return {
        "label": label,
        "approved": result.approved,
        "iterations": result.iterations,
        "wall_time_s": round(elapsed, 1),
        "artifact_count": len(result.enhanced_artifacts),
        "artifacts": list(result.enhanced_artifacts.keys()),
    }


async def main():
    # Verify API key
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)
    print(f"✓ OPENAI_API_KEY set ({api_key[:12]}...)")

    results = []

    # Test 1: FastAPI (microservices focus)
    try:
        profile, kg = build_fastapi_profile()
        r = await run_single_repo("FastAPI (Microservices)", profile, kg)
        results.append(r)
    except Exception as e:
        print(f"\n✗ FastAPI test FAILED: {e}")
        traceback.print_exc()
        results.append({"label": "FastAPI", "error": str(e)})

    # Test 2: HuggingFace Transformers (ML focus)
    try:
        profile, kg = build_transformers_profile()
        r = await run_single_repo("HuggingFace Transformers (ML)", profile, kg)
        results.append(r)
    except Exception as e:
        print(f"\n✗ Transformers test FAILED: {e}")
        traceback.print_exc()
        results.append({"label": "Transformers", "error": str(e)})

    # Final summary
    print("\n" + "=" * 70)
    print("  FINAL RESULTS")
    print("=" * 70)
    for r in results:
        status = "✓ PASS" if r.get("approved") else ("✗ FAIL" if "error" not in r else "✗ ERROR")
        label = r["label"]
        if "error" in r:
            print(f"  {status}  {label}: {r['error']}")
        else:
            print(
                f"  {status}  {label}: "
                f"{r['artifact_count']} artifacts, "
                f"{r['iterations']} iter, "
                f"{r['wall_time_s']}s"
            )
    print()


if __name__ == "__main__":
    asyncio.run(main())
