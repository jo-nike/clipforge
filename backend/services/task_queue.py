"""
Async Task Queue Service for Background Processing
Handles long-running video processing tasks to prevent request timeouts
"""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

from core.logging import get_logger

logger = get_logger("task_queue")


class TaskStatus(str, Enum):
    """Task status enumeration"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskResult:
    """Represents a task execution result"""

    def __init__(
        self,
        task_id: str,
        status: TaskStatus,
        result: Any = None,
        error: Optional[str] = None,
        created_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ):
        self.task_id = task_id
        self.status = status
        self.result = result
        self.error = error
        self.created_at = created_at or datetime.now()
        self.completed_at = completed_at


class AsyncTaskQueue:
    """Simple async task queue for background processing"""

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskResult] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self.logger = get_logger("async_task_queue")

    async def submit_task(
        self,
        task_func: Callable[..., Awaitable[Any]],
        *args: Any,
        task_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Submit a task for background execution"""

        if task_id is None:
            task_id = str(uuid.uuid4())

        # Initialize task result
        task_result = TaskResult(
            task_id=task_id, status=TaskStatus.PENDING, created_at=datetime.now()
        )
        self._tasks[task_id] = task_result

        # Create and start the background task
        async_task = asyncio.create_task(self._execute_task(task_id, task_func, *args, **kwargs))
        self._running_tasks[task_id] = async_task

        self.logger.info(f"Submitted task {task_id} for background execution")
        return task_id

    async def _execute_task(
        self, task_id: str, task_func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> None:
        """Execute a task in the background"""

        try:
            # Update status to processing
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.PROCESSING

            self.logger.info(f"Starting execution of task {task_id}")

            # Execute the task function
            result = await task_func(*args, **kwargs)

            # Update with successful result
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.COMPLETED
                self._tasks[task_id].result = result
                self._tasks[task_id].completed_at = datetime.now()

            self.logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            # Update with error
            error_msg = f"Task execution failed: {str(e)}"
            self.logger.error(f"Task {task_id} failed: {error_msg}")

            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.FAILED
                self._tasks[task_id].error = error_msg
                self._tasks[task_id].completed_at = datetime.now()

        finally:
            # Cleanup running task reference
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]

    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """Get current status of a task"""
        return self._tasks.get(task_id)

    def is_task_complete(self, task_id: str) -> bool:
        """Check if a task is complete (either success or failure)"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        return task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]

    def cleanup_task(self, task_id: str) -> None:
        """Remove task from memory (call after client retrieves result)"""
        if task_id in self._tasks:
            del self._tasks[task_id]
        if task_id in self._running_tasks:
            # Cancel if still running
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

    def get_active_task_count(self) -> int:
        """Get number of currently active tasks"""
        return len(self._running_tasks)

    def get_total_task_count(self) -> int:
        """Get total number of tracked tasks"""
        return len(self._tasks)


# Global task queue instance
task_queue = AsyncTaskQueue()


def get_task_queue() -> AsyncTaskQueue:
    """Dependency injection for task queue"""
    return task_queue
