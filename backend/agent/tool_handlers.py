"""Tool execution — dispatches tool_use blocks to per-tool handlers.

Every handler returns a dict {"ok": bool, "result": ..., "error": str}.
Enforcement failures are returned as {"ok": False, ...}; the runner forwards
this back to the model as an error block so the model self-corrects.

Raises ToolExecutionError only for unknown tools — that is a programmer error,
not a gate failure.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.enforcement.critique_quality import CritiqueQualityError
from backend.enforcement.review_loop import ReviewLoop, ReviewLoopError
from backend.enforcement.research_loop import ResearchLoop, ResearchLoopError


class ToolExecutionError(Exception):
    """Raised when a tool name is unknown (programmer error, not gate failure)."""


def _safe_join(root: str, relative: str) -> Path:
    root_p = Path(root).resolve()
    target = (root_p / relative).resolve()
    if root_p not in target.parents and root_p != target.parent and root_p != target:
        raise ValueError(f"path {relative!r} escapes project root")
    return target


class ToolExecutor:
    def __init__(
        self, *,
        review_loop: ReviewLoop | None = None,
        research_loop: ResearchLoop | None = None,
        project_root: str = ".",
    ):
        self.review_loop = review_loop
        self.research_loop = research_loop
        self.project_root = project_root

    def dispatch(self, name: str, args: dict) -> dict:
        handler = getattr(self, f"_h_{name}", None)
        if handler is None:
            raise ToolExecutionError(f"unknown tool: {name}")
        try:
            return handler(args)
        except (ReviewLoopError, ResearchLoopError, CritiqueQualityError, ValueError) as e:
            return {"ok": False, "error": str(e)}

    # ---- file / search ----

    def _h_read_file(self, args: dict) -> dict:
        p = _safe_join(self.project_root, args["path"])
        if not p.exists():
            return {"ok": False, "error": f"file not found: {args['path']}"}
        return {"ok": True, "result": p.read_text(encoding="utf-8")}

    def _h_write_file(self, args: dict) -> dict:
        try:
            p = _safe_join(self.project_root, args["path"])
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return {"ok": True, "result": f"wrote {args['path']}"}

    def _h_web_search(self, args: dict) -> dict:
        # v1: real web search is deferred; returns a stub that the runner may
        # override by injecting a real search function (for test isolation).
        return {"ok": True, "result": [{"title": "stub", "url": "", "snippet": ""}]}

    # ---- review loop ----

    def _h_submit_draft(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.submit_draft(artifacts=args["artifacts"])
        return {"ok": True, "result": {"status": self.review_loop.status,
                                       "iteration": self.review_loop.iteration}}

    def _h_submit_revision(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.submit_revision(artifacts=args["artifacts"])
        return {"ok": True, "result": {"status": self.review_loop.status,
                                       "iteration": self.review_loop.iteration}}

    def _h_submit_review(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.submit_review(
            verdict=args["verdict"], critique=args["critique"],
        )
        return {"ok": True, "result": {"status": self.review_loop.status}}

    def _h_finalize(self, args: dict) -> dict:
        assert self.review_loop is not None
        self.review_loop.finalize()
        return {"ok": True, "result": {"finalized": True}}

    # ---- research loop ----

    def _h_add_candidate(self, args: dict) -> dict:
        assert self.research_loop is not None
        score = self.research_loop.add_candidate(
            name=args["name"], scores=args["scores"],
        )
        return {"ok": True, "result": {
            "weighted_score": score,
            "leader": self.research_loop.leader,
        }}

    def _h_challenge_leader(self, args: dict) -> dict:
        assert self.research_loop is not None
        self.research_loop.challenge(
            leader=args["leader"], result=args["result"], evidence=args["evidence"],
        )
        return {"ok": True, "result": {
            "leader_streak": self.research_loop.leader_streak,
        }}

    def _h_score_iteration(self, args: dict) -> dict:
        assert self.research_loop is not None
        self.research_loop.score_iteration()
        return {"ok": True, "result": {"iteration": self.research_loop.iteration}}

    def _h_record_final(self, args: dict) -> dict:
        assert self.research_loop is not None
        self.research_loop.record_final(recommendation=args["recommendation"])
        return {"ok": True, "result": {"recommendation": args["recommendation"]}}
