from .service import (
    LearnerStateEvent,
    LearnerStateOutboxItem,
    LearnerStateOutboxService,
    LearningPlanPageRecord,
    LearningPlanRecord,
    LearnerStateSnapshot,
    LearnerStateUpdateResult,
    LearnerStateService,
    get_learner_state_service,
)
from .flusher import LearnerStateOutboxFlusher, LearnerStateOutboxFlushResult, LearnerStateOutboxWriter
from .heartbeat import LearnerHeartbeatJob, LearnerHeartbeatJobService
from .runtime import LearnerHeartbeatExecutor, LearnerStateRuntime, LearnerStateRuntimeConfig, create_default_learner_state_runtime
from .supabase_store import (
    LearnerStateSupabaseClient,
    LearnerStateSupabaseCoreStore,
    LearnerStateSupabaseSyncCoreStore,
)
from .supabase_writer import LearnerStateSupabaseWriteResult, LearnerStateSupabaseWriter

try:
    from .overlay_service import BotLearnerOverlayService, get_bot_learner_overlay_service
except ModuleNotFoundError:  # pragma: no cover - optional phase-2 module
    BotLearnerOverlayService = None

    def get_bot_learner_overlay_service():
        raise RuntimeError("Bot learner overlay service is not available")

__all__ = [
    "LearnerHeartbeatJob",
    "LearnerHeartbeatJobService",
    "LearnerHeartbeatExecutor",
    "LearnerStateEvent",
    "LearnerStateOutboxFlusher",
    "LearnerStateOutboxFlushResult",
    "LearnerStateOutboxItem",
    "LearnerStateOutboxService",
    "LearnerStateOutboxWriter",
    "LearnerStateRuntime",
    "LearnerStateRuntimeConfig",
    "BotLearnerOverlayService",
    "LearnerStateSupabaseClient",
    "LearnerStateSupabaseCoreStore",
    "LearnerStateSupabaseSyncCoreStore",
    "LearnerStateSupabaseWriteResult",
    "LearnerStateSupabaseWriter",
    "LearningPlanPageRecord",
    "LearningPlanRecord",
    "LearnerStateSnapshot",
    "LearnerStateUpdateResult",
    "LearnerStateService",
    "create_default_learner_state_runtime",
    "get_bot_learner_overlay_service",
    "get_learner_state_service",
]
