#!/usr/bin/env python
"""
GuideManager - Guided Learning Session Manager
Manages the complete lifecycle of learning sessions
"""

import asyncio
from dataclasses import asdict, dataclass, field
import json
from datetime import datetime
from pathlib import Path
import time
from typing import Any
import uuid

import yaml

from deeptutor.logging import get_logger
from deeptutor.services.learning_plan import LearningPlanService
from deeptutor.services.config import load_config_with_main, parse_language
from deeptutor.services.path_service import get_path_service
from deeptutor.services.tutor_state.service import UserTutorStateService

from .agents import ChatAgent, DesignAgent, InteractiveAgent, SummaryAgent


@dataclass
class GuidedSession:
    """Guided learning session"""

    session_id: str
    notebook_id: str
    notebook_name: str
    created_at: float
    user_id: str = ""
    source_bot_id: str = ""
    knowledge_points: list[dict[str, Any]] = field(default_factory=list)
    current_index: int = -1
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    status: str = "initialized"  # initialized, learning, completed
    html_pages: dict[str, str] = field(default_factory=dict)
    page_statuses: dict[str, str] = field(default_factory=dict)
    page_errors: dict[str, str] = field(default_factory=dict)
    summary: str = ""
    notebook_context: str = ""
    source_material_refs_json: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuidedSession":
        session_data = dict(data)

        current_html = str(session_data.pop("current_html", "") or "")
        session_data.pop("current_knowledge", None)
        session_data.pop("pages", None)
        session_data.pop("page_count", None)
        session_data.pop("ready_count", None)
        session_data.pop("progress", None)
        session_data.pop("updated_at", None)
        current_index = int(session_data.get("current_index", -1))
        html_pages = dict(session_data.get("html_pages") or {})
        page_statuses = dict(session_data.get("page_statuses") or {})
        page_errors = dict(session_data.get("page_errors") or {})

        if current_html and not html_pages and current_index >= 0:
            html_pages[str(current_index)] = current_html
            page_statuses[str(current_index)] = "ready"

        session_data.setdefault("current_index", current_index)
        session_data.setdefault("chat_history", [])
        session_data.setdefault("status", "initialized")
        session_data.setdefault("summary", "")
        session_data["html_pages"] = html_pages
        session_data["page_statuses"] = page_statuses
        session_data["page_errors"] = page_errors
        return cls(**session_data)


class _GuideOutputPathService:
    def __init__(self, guide_dir: Path) -> None:
        self._guide_dir = guide_dir

    def get_guide_dir(self) -> Path:
        self._guide_dir.mkdir(parents=True, exist_ok=True)
        return self._guide_dir


class GuideManager:
    """Guided learning manager"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        api_version: str | None = None,
        language: str | None = None,
        output_dir: str | None = None,
        config_path: str | None = None,
        binding: str = "openai",
    ):
        """
        Initialize manager

        Args:
            api_key: API key
            base_url: API endpoint
            api_version: API version (for Azure OpenAI)
            language: Language setting (if None, read from config file)
            output_dir: Output directory
            config_path: Configuration file path (if None, use default path)
            binding: LLM provider binding
        """
        self.api_key = api_key
        self.base_url = base_url
        self.api_version = api_version
        self.binding = binding

        if config_path is None:
            from deeptutor.services.config import PROJECT_ROOT

            config = load_config_with_main("main.yaml", PROJECT_ROOT)
        else:
            config_path = Path(config_path)
            if config_path.exists():
                try:
                    with open(config_path, encoding="utf-8") as f:
                        config = yaml.safe_load(f) or {}
                except Exception:
                    config = {}
            else:
                config = {}

        # Initialize logger (from config)
        log_dir = config.get("paths", {}).get("user_log_dir") or config.get("logging", {}).get(
            "log_dir"
        )
        self.logger = get_logger("Guide", log_dir=log_dir)

        if language is None:
            # Get language config (unified in config/main.yaml system.language)
            lang_config = config.get("system", {}).get("language", "zh")
            self.language = parse_language(lang_config)
            self.logger.info(f"Language setting loaded from config: {self.language}")
        else:
            # If explicitly specified, also parse it to ensure consistency
            self.language = parse_language(language)
            self.logger.info(f"Using explicitly specified language setting: {self.language}")

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            # Get output_dir from config (already loaded above)
            output_dir_from_config = config.get("system", {}).get("output_dir")
            if output_dir_from_config:
                self.output_dir = Path(output_dir_from_config)
            else:
                # Fallback to default path using PathService
                path_service = get_path_service()
                self.output_dir = path_service.get_guide_dir()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.design_agent = DesignAgent(
            api_key,
            base_url,
            language=self.language,
            api_version=self.api_version,
            binding=self.binding,
        )
        self.interactive_agent = InteractiveAgent(
            api_key,
            base_url,
            language=self.language,
            api_version=self.api_version,
            binding=self.binding,
        )
        self.chat_agent = ChatAgent(
            api_key,
            base_url,
            language=self.language,
            api_version=self.api_version,
            binding=self.binding,
        )
        self.summary_agent = SummaryAgent(
            api_key,
            base_url,
            language=self.language,
            api_version=self.api_version,
            binding=self.binding,
        )

        self._sessions: dict[str, GuidedSession] = {}
        self._generation_tasks: dict[str, asyncio.Task[None]] = {}
        self._learning_plan_service = LearningPlanService(
            path_service=_GuideOutputPathService(self.output_dir),
        )
        self.max_parallel_generations = 2

    def _get_session_file(self, session_id: str) -> Path:
        """Get session file path"""
        return self.output_dir / f"session_{session_id}.json"

    def _save_session(self, session: GuidedSession):
        """Save session to file"""
        filepath = self._get_session_file(session.session_id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        self._sessions[session.session_id] = session
        self._persist_learning_plan(session)

    def _delete_session(self, session_id: str):
        """Delete a session from memory and disk."""
        self._sessions.pop(session_id, None)
        self._learning_plan_service.delete_plan(session_id)
        filepath = self._get_session_file(session_id)
        if filepath.exists():
            filepath.unlink()

    def _load_session(self, session_id: str) -> GuidedSession | None:
        """Load session from file"""
        if session_id in self._sessions:
            return self._sessions[session_id]

        plan_view = self._learning_plan_service.read_guided_session_view(session_id)
        if plan_view:
            session = GuidedSession.from_dict(plan_view)
            self._sessions[session_id] = session
            return session

        filepath = self._get_session_file(session_id)
        if filepath.exists():
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            session = GuidedSession.from_dict(data)
            self._sessions[session_id] = session
            self._persist_learning_plan(session)
            return session
        return None

    def _initialize_page_statuses(self, session: GuidedSession):
        """Ensure every knowledge point has an initial page status."""
        for index, _knowledge in enumerate(session.knowledge_points):
            key = str(index)
            session.page_statuses.setdefault(key, "pending")
            session.page_errors.setdefault(key, "")

    def _count_ready_pages(self, session: GuidedSession) -> int:
        return sum(1 for status in session.page_statuses.values() if status == "ready")

    def _calculate_progress(self, session: GuidedSession) -> int:
        total_points = len(session.knowledge_points)
        if total_points == 0:
            return 0
        return int((self._count_ready_pages(session) / total_points) * 100)

    def _has_active_generation_task(self, session_id: str) -> bool:
        task = self._generation_tasks.get(session_id)
        return bool(task and not task.done())

    def _clear_generation_task(self, session_id: str):
        task = self._generation_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def _resolve_learner_identity(
        self,
        session: GuidedSession,
        user_id: str | None = None,
        source_bot_id: str | None = None,
    ) -> tuple[str, str]:
        resolved_user_id = str(user_id or session.user_id or "").strip()
        resolved_source_bot_id = str(source_bot_id or session.source_bot_id or "").strip()
        return resolved_user_id, resolved_source_bot_id

    async def _writeback_learner_state(
        self,
        session: GuidedSession,
        summary: str,
        *,
        user_id: str | None = None,
        source_bot_id: str | None = None,
    ) -> bool:
        resolved_user_id, resolved_source_bot_id = self._resolve_learner_identity(
            session,
            user_id=user_id,
            source_bot_id=source_bot_id,
        )
        summary_text = str(summary or "").strip()
        if not resolved_user_id or not summary_text:
            return False

        learner_state_service = UserTutorStateService()
        await learner_state_service.record_guide_completion(
            user_id=resolved_user_id,
            guide_id=session.session_id,
            notebook_name=session.notebook_name,
            summary=summary_text,
            knowledge_points=session.knowledge_points,
            source_bot_id=resolved_source_bot_id or None,
        )
        await learner_state_service.refresh_from_turn(
            user_id=resolved_user_id,
            user_message=str(session.notebook_context or session.notebook_name or "Guided learning completion"),
            assistant_message=summary_text,
            session_id=session.session_id,
            capability="guide" if not resolved_source_bot_id else f"guide:{resolved_source_bot_id}",
            language=self.language,
            timestamp=datetime.now().isoformat(),
            source_bot_id=resolved_source_bot_id or None,
        )
        return True

    @staticmethod
    def _build_learning_plan_source_refs(
        user_input: str,
        notebook_context: str,
    ) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        if user_input.strip():
            refs.append({"kind": "user_input", "content": user_input.strip()})
        if notebook_context.strip():
            refs.append({"kind": "notebook_context", "content": notebook_context.strip()})
        return refs

    def _persist_learning_plan(self, session: GuidedSession) -> None:
        pages: list[dict[str, Any]] = []
        for index, knowledge in enumerate(session.knowledge_points):
            key = str(index)
            pages.append(
                {
                    "page_index": index,
                    "knowledge_title": str(knowledge.get("knowledge_title", "") or "").strip(),
                    "knowledge_summary": str(knowledge.get("knowledge_summary", "") or "").strip(),
                    "user_difficulty": str(knowledge.get("user_difficulty", "") or "").strip(),
                    "html": str(session.html_pages.get(key, "") or "").strip(),
                    "page_status": str(session.page_statuses.get(key, "pending") or "pending"),
                    "page_error": str(session.page_errors.get(key, "") or "").strip(),
                }
            )

        existing = self._learning_plan_service.read_plan(session.session_id)
        fields = {
            "user_id": str(session.user_id or "").strip(),
            "source_bot_id": str(session.source_bot_id or "").strip(),
            "notebook_id": str(session.notebook_id or "").strip(),
            "notebook_name": str(session.notebook_name or "").strip(),
            "notebook_context": str(session.notebook_context or "").strip(),
            "source_material_refs_json": list(session.source_material_refs_json or []),
            "status": str(session.status or "initialized"),
            "current_index": int(session.current_index),
            "chat_history": list(session.chat_history or []),
            "summary": str(session.summary or "").strip(),
            "created_at": float(session.created_at),
        }
        if existing is None:
            self._learning_plan_service.create_plan(
                session_id=session.session_id,
                pages=pages,
                **fields,
            )
            return

        self._learning_plan_service.update_plan(session.session_id, **fields)
        for page in pages:
            page_index = int(page.get("page_index", 0) or 0)
            page_fields = {
                key: value
                for key, value in page.items()
                if key not in {"page_index", "session_id"}
            }
            self._learning_plan_service.upsert_page(
                session.session_id,
                page_index,
                **page_fields,
            )

    async def _sync_learning_plan(
        self,
        session: GuidedSession,
        *,
        source_material_refs_json: list[dict[str, Any]] | None = None,
        page_index: int | None = None,
        page_status: str | None = None,
        html_content: str = "",
        error_message: str = "",
    ) -> bool:
        resolved_user_id, resolved_source_bot_id = self._resolve_learner_identity(session)
        if not resolved_user_id:
            return False
        if source_material_refs_json is not None:
            session.source_material_refs_json = list(source_material_refs_json)
        if page_index is not None:
            key = str(page_index)
            session.page_statuses[key] = page_status or session.page_statuses.get(key, "pending")
            session.page_errors[key] = error_message
            if html_content:
                session.html_pages[key] = html_content
        session.user_id = resolved_user_id
        session.source_bot_id = resolved_source_bot_id
        self._persist_learning_plan(session)
        return True

    async def _generate_single_page(self, session_id: str, knowledge_index: int) -> dict[str, Any]:
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        if knowledge_index < 0 or knowledge_index >= len(session.knowledge_points):
            return {"success": False, "error": "Knowledge point does not exist"}

        key = str(knowledge_index)
        knowledge = session.knowledge_points[knowledge_index]
        session.page_statuses[key] = "generating"
        session.page_errors[key] = ""
        self._save_session(session)

        result = await self.interactive_agent.process(knowledge=knowledge)
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        if result.get("success"):
            html = result.get("html", "")
            if html:
                session.html_pages[key] = html
            session.page_statuses[key] = "ready"
            session.page_errors[key] = result.get("error", "")
            self._save_session(session)
            try:
                await self._sync_learning_plan(
                    session,
                    page_index=knowledge_index,
                    page_status=session.page_statuses.get(key, "ready"),
                    html_content=session.html_pages.get(key, ""),
                    error_message=session.page_errors.get(key, ""),
                )
            except Exception:
                self.logger.debug(
                    f"Learning plan page sync failed for guided session {session.session_id} page {knowledge_index}",
                    exc_info=True,
                )
            return result

        retryable = bool(result.get("retryable"))
        session.page_statuses[key] = "pending" if retryable else "failed"
        session.page_errors[key] = result.get("error", "Failed to generate page")
        self._save_session(session)
        try:
            await self._sync_learning_plan(
                session,
                page_index=knowledge_index,
                page_status=session.page_statuses.get(key, "failed"),
                html_content=session.html_pages.get(key, ""),
                error_message=session.page_errors.get(key, ""),
            )
        except Exception:
            self.logger.debug(
                f"Learning plan page sync failed for guided session {session.session_id} page {knowledge_index}",
                exc_info=True,
            )
        return result

    async def _generate_all_pages_background(
        self, session_id: str, indices: list[int] | None = None
    ) -> None:
        session = self._load_session(session_id)
        if not session:
            return

        if indices is None:
            page_indices = list(range(len(session.knowledge_points)))
        else:
            page_indices = sorted({index for index in indices if 0 <= index < len(session.knowledge_points)})

        if not page_indices:
            return

        queue: asyncio.PriorityQueue[tuple[int, int]] = asyncio.PriorityQueue()
        for index in page_indices:
            await queue.put((index, 0))

        shared_state = {"backoff_until": 0.0}

        async def worker():
            while True:
                index, attempt = await queue.get()
                try:
                    delay = shared_state["backoff_until"] - time.time()
                    if delay > 0:
                        await asyncio.sleep(delay)

                    result = await self._generate_single_page(session_id, index)
                    if result.get("retryable") and attempt < 2:
                        backoff_seconds = 2**attempt
                        shared_state["backoff_until"] = max(
                            shared_state["backoff_until"], time.time() + backoff_seconds
                        )
                        await queue.put((index, attempt + 1))
                    elif result.get("retryable"):
                        failed_session = self._load_session(session_id)
                        if failed_session:
                            key = str(index)
                            failed_session.page_statuses[key] = "failed"
                            failed_session.page_errors[key] = result.get(
                                "error", "Failed after retries"
                            )
                            self._save_session(failed_session)
                            try:
                                await self._sync_learning_plan(
                                    failed_session,
                                    page_index=index,
                                    page_status=failed_session.page_statuses.get(key, "failed"),
                                    html_content=failed_session.html_pages.get(key, ""),
                                    error_message=failed_session.page_errors.get(key, ""),
                                )
                            except Exception:
                                self.logger.debug(
                                    f"Learning plan sync failed for guided session {failed_session.session_id} page {index}",
                                    exc_info=True,
                                )
                finally:
                    queue.task_done()

        workers = [
            asyncio.create_task(worker()) for _ in range(min(self.max_parallel_generations, len(page_indices)))
        ]

        try:
            await queue.join()
        finally:
            for worker_task in workers:
                worker_task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    def _schedule_generation_task(self, session_id: str, indices: list[int] | None = None):
        if self._has_active_generation_task(session_id):
            return

        task = asyncio.create_task(self._generate_all_pages_background(session_id, indices))
        self._generation_tasks[session_id] = task

        def _cleanup(_task: asyncio.Task[None]):
            self._generation_tasks.pop(session_id, None)

        task.add_done_callback(_cleanup)

    async def create_session(
        self,
        user_input: str,
        display_title: str | None = None,
        notebook_context: str = "",
        user_id: str | None = None,
        source_bot_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create new learning session

        Args:
            user_input: User's learning request

        Returns:
            Session creation result
        """
        if not user_input.strip():
            return {
                "success": False,
                "error": "User input cannot be empty",
                "session_id": None,
            }

        session_id = str(uuid.uuid4())[:8]

        design_result = await self.design_agent.process(user_input=user_input)

        if not design_result.get("success"):
            return {
                "success": False,
                "error": design_result.get("error", "Failed to design learning plan"),
                "session_id": None,
            }

        knowledge_points = design_result.get("knowledge_points", [])

        if not knowledge_points:
            return {
                "success": False,
                "error": "No knowledge points identified from user input",
                "session_id": None,
            }

        session_title = (display_title or user_input).strip().replace("\n", " ")[:50]

        session = GuidedSession(
            session_id=session_id,
            notebook_id="user_input",
            notebook_name=session_title or "Guided Learning",
            created_at=time.time(),
            user_id=str(user_id or "").strip(),
            source_bot_id=str(source_bot_id or "").strip(),
            knowledge_points=knowledge_points,
            current_index=-1,
            status="initialized",
            notebook_context=notebook_context,
            source_material_refs_json=self._build_learning_plan_source_refs(
                user_input,
                notebook_context,
            ),
        )
        self._initialize_page_statuses(session)

        self._save_session(session)
        try:
            await self._sync_learning_plan(
                session,
                source_material_refs_json=session.source_material_refs_json,
            )
        except Exception:
            self.logger.debug(
                f"Learning plan sync failed for created guided session {session.session_id}",
                exc_info=True,
            )

        return {
            "success": True,
            "session_id": session_id,
            "knowledge_points": knowledge_points,
            "total_points": len(knowledge_points),
            "message": f"Learning plan created with {len(knowledge_points)} knowledge points",
        }

    def _get_learning_state(
        self, knowledge_points: list[dict[str, Any]], current_index: int
    ) -> dict[str, Any]:
        """
        Get learning state information (internal helper method)

        Args:
            knowledge_points: Knowledge point list
            current_index: Current knowledge point index

        Returns:
            Learning state information
        """
        total_points = len(knowledge_points)

        if total_points == 0:
            return {"success": False, "error": "No knowledge points to learn", "status": "empty"}

        if current_index >= total_points:
            return {
                "success": True,
                "current_index": current_index,
                "current_knowledge": None,
                "status": "completed",
                "progress_percentage": 100,
                "total_points": total_points,
                "message": "🎉 Congratulations! You have completed learning all knowledge points!",
            }

        current_knowledge = knowledge_points[current_index]
        progress = int((current_index / total_points) * 100)

        message = f"📚 Starting to learn knowledge point {current_index + 1}: {current_knowledge.get('knowledge_title', '')}"

        return {
            "success": True,
            "current_index": current_index,
            "current_knowledge": current_knowledge,
            "status": "learning",
            "progress_percentage": progress,
            "total_points": total_points,
            "remaining_points": total_points - current_index - 1,
            "message": message,
        }

    async def start_learning(self, session_id: str) -> dict[str, Any]:
        """
        Start learning the first knowledge point

        Args:
            session_id: Session ID

        Returns:
            First knowledge point information and interactive page
        """
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        session.current_index = 0
        session.status = "learning"
        self._initialize_page_statuses(session)

        session.chat_history.append(
            {
                "role": "system",
                "content": "Started guided learning. Interactive pages are now generating in parallel.",
                "knowledge_index": 0,
                "timestamp": time.time(),
            }
        )

        self._save_session(session)
        try:
            await self._sync_learning_plan(session)
        except Exception:
            self.logger.debug(
                f"Learning plan sync failed for guided session {session.session_id}",
                exc_info=True,
            )
        self._schedule_generation_task(session_id)

        return {
            "success": True,
            "current_index": 0,
            "current_knowledge": session.knowledge_points[0] if session.knowledge_points else None,
            "html": session.html_pages.get("0", ""),
            "page_statuses": session.page_statuses,
            "progress": self._calculate_progress(session),
            "total_points": len(session.knowledge_points),
            "message": "Interactive pages are generating in parallel. Open any page as soon as it is ready.",
        }

    async def navigate_to_knowledge(self, session_id: str, knowledge_index: int) -> dict[str, Any]:
        """Navigate to any knowledge point."""
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        if knowledge_index < 0 or knowledge_index >= len(session.knowledge_points):
            return {"success": False, "error": "Knowledge point does not exist"}

        self._initialize_page_statuses(session)
        session.current_index = knowledge_index
        self._save_session(session)
        try:
            await self._sync_learning_plan(session)
        except Exception:
            self.logger.debug(
                f"Learning plan sync failed for guided session {session.session_id}",
                exc_info=True,
            )

        if not self._has_active_generation_task(session_id):
            pending_indices = [
                index
                for index, _knowledge in enumerate(session.knowledge_points)
                if session.page_statuses.get(str(index)) in {"pending", "generating"}
            ]
            if pending_indices:
                self._schedule_generation_task(session_id, pending_indices)

        key = str(knowledge_index)
        return {
            "success": True,
            "current_index": knowledge_index,
            "current_knowledge": session.knowledge_points[knowledge_index],
            "html": session.html_pages.get(key, ""),
            "page_status": session.page_statuses.get(key, "pending"),
            "page_error": session.page_errors.get(key, ""),
            "progress": self._calculate_progress(session),
            "total_points": len(session.knowledge_points),
            "message": f"Viewing knowledge point {knowledge_index + 1}.",
        }

    async def complete_learning(
        self,
        session_id: str,
        user_id: str | None = None,
        source_bot_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate the final learning summary."""
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        summary_result = await self.summary_agent.process(
            notebook_name=session.notebook_name,
            knowledge_points=session.knowledge_points,
            chat_history=session.chat_history,
        )

        session.status = "completed"
        session.summary = summary_result.get("summary", "")
        resolved_user_id, resolved_source_bot_id = self._resolve_learner_identity(
            session,
            user_id=user_id,
            source_bot_id=source_bot_id,
        )
        if resolved_user_id:
            session.user_id = resolved_user_id
        if resolved_source_bot_id:
            session.source_bot_id = resolved_source_bot_id
        session.chat_history.append(
            {
                "role": "system",
                "content": "Congratulations on completing guided learning!",
                "timestamp": time.time(),
            }
        )
        self._save_session(session)
        try:
            await self._sync_learning_plan(session)
        except Exception:
            self.logger.debug(
                f"Learning plan sync failed for completed guided session {session.session_id}",
                exc_info=True,
            )
        try:
            await self._writeback_learner_state(
                session,
                session.summary,
                user_id=resolved_user_id,
                source_bot_id=resolved_source_bot_id,
            )
        except Exception:
            self.logger.debug(
                f"Learner state writeback failed for guided session {session.session_id}",
                exc_info=True,
            )

        return {
            "success": True,
            "status": "completed",
            "summary": session.summary,
            "progress": 100,
            "message": "Guided learning completed.",
        }

    async def chat(
        self, session_id: str, user_message: str, knowledge_index: int | None = None
    ) -> dict[str, Any]:
        """
        Process user chat message

        Args:
            session_id: Session ID
            user_message: User message

        Returns:
            Assistant's answer
        """
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        if session.status != "learning":
            return {"success": False, "error": "Not currently in learning state"}

        current_index = session.current_index if knowledge_index is None else knowledge_index
        if current_index < 0 or current_index >= len(session.knowledge_points):
            return {"success": False, "error": "Knowledge point does not exist"}

        current_knowledge = session.knowledge_points[current_index]
        current_html = session.html_pages.get(str(current_index), "")

        current_history = [
            msg
            for msg in session.chat_history
            if msg.get("knowledge_index") == current_index
        ]

        user_msg = {
            "role": "user",
            "content": user_message,
            "knowledge_index": current_index,
            "timestamp": time.time(),
        }
        session.chat_history.append(user_msg)

        chat_result = await self.chat_agent.process(
            knowledge=current_knowledge,
            chat_history=current_history,
            user_question=user_message,
            current_html=current_html,
        )

        assistant_msg = {
            "role": "assistant",
            "content": chat_result.get("answer", ""),
            "knowledge_index": current_index,
            "timestamp": time.time(),
        }
        session.chat_history.append(assistant_msg)

        self._save_session(session)

        return {
            "success": True,
            "answer": chat_result.get("answer", ""),
            "knowledge_index": current_index,
        }

    async def fix_html(self, session_id: str, bug_description: str) -> dict[str, Any]:
        """
        Fix HTML page bug

        Args:
            session_id: Session ID
            bug_description: Bug description

        Returns:
            Fixed HTML
        """
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        if session.current_index < 0:
            return {"success": False, "error": "No active knowledge point selected"}

        current_knowledge = session.knowledge_points[session.current_index]

        result = await self.interactive_agent.process(
            knowledge=current_knowledge, retry_with_bug=bug_description
        )

        if result.get("success"):
            session.html_pages[str(session.current_index)] = result.get("html", "")
            session.page_statuses[str(session.current_index)] = "ready"
            self._save_session(session)
            try:
                await self._sync_learning_plan(
                    session,
                    page_index=session.current_index,
                    page_status=session.page_statuses.get(str(session.current_index), "ready"),
                    html_content=session.html_pages.get(str(session.current_index), ""),
                    error_message=session.page_errors.get(str(session.current_index), ""),
                )
            except Exception:
                self.logger.debug(
                    f"Learning plan sync failed for fixed guided session {session.session_id} page {session.current_index}",
                    exc_info=True,
                )

        return result

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session information"""
        session = self._load_session(session_id)
        if session:
            self._initialize_page_statuses(session)
            self._save_session(session)
            return session.to_dict()
        return None

    def get_session_pages(self, session_id: str) -> dict[str, Any] | None:
        """Get page generation status for a session."""
        session = self._load_session(session_id)
        if not session:
            return None

        self._initialize_page_statuses(session)
        if session.status == "learning" and not self._has_active_generation_task(session_id):
            pending_indices = [
                index
                for index, _knowledge in enumerate(session.knowledge_points)
                if session.page_statuses.get(str(index)) in {"pending", "generating"}
            ]
            if pending_indices:
                self._schedule_generation_task(session_id, pending_indices)

        return {
            "session_id": session.session_id,
            "current_index": session.current_index,
            "status": session.status,
            "page_statuses": session.page_statuses,
            "page_errors": session.page_errors,
            "html_pages": session.html_pages,
            "progress": self._calculate_progress(session),
            "total_points": len(session.knowledge_points),
        }

    def get_current_html(self, session_id: str) -> str | None:
        """Get current HTML page"""
        session = self._load_session(session_id)
        if not session or session.current_index < 0:
            return None
        return session.html_pages.get(str(session.current_index))

    async def retry_page(self, session_id: str, page_index: int) -> dict[str, Any]:
        """Retry a failed or pending page generation."""
        session = self._load_session(session_id)
        if not session:
            return {"success": False, "error": "Session does not exist"}

        if page_index < 0 or page_index >= len(session.knowledge_points):
            return {"success": False, "error": "Knowledge point does not exist"}

        key = str(page_index)
        session.page_statuses[key] = "pending"
        session.page_errors[key] = ""
        self._save_session(session)
        self._schedule_generation_task(session_id, [page_index])

        return {
            "success": True,
            "page_index": page_index,
            "page_status": session.page_statuses.get(key, "pending"),
            "message": f"Retrying knowledge point {page_index + 1}.",
        }

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions with summary metadata (no html_pages / chat_history)."""
        return [
            {
                "session_id": item.get("session_id", ""),
                "topic": item.get("notebook_name", ""),
                "status": item.get("status", "initialized"),
                "created_at": item.get("created_at", 0),
                "total_points": item.get("page_count", 0),
                "ready_count": item.get("ready_count", 0),
                "progress": item.get("progress", 0),
            }
            for item in self._learning_plan_service.list_plans()
        ]

    async def reset_session(self, session_id: str) -> dict[str, Any]:
        """Detach from a session (cancel tasks, clear cache, but keep the file for history)."""
        self._clear_generation_task(session_id)
        self._sessions.pop(session_id, None)
        return {"success": True, "message": "Session reset"}

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """Permanently delete a session from memory and disk."""
        self._clear_generation_task(session_id)
        self._delete_session(session_id)
        return {"success": True, "message": "Session deleted"}
