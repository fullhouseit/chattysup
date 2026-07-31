"""Background workers: channel polling and conversation housekeeping."""
from .scheduler import Scheduler, scheduler, tick
from .supervisor import (
    PollingSupervisor,
    reload_inbox,
    remove_inbox,
    supervisor,
)

__all__ = [
    "PollingSupervisor",
    "Scheduler",
    "reload_inbox",
    "remove_inbox",
    "scheduler",
    "supervisor",
    "start_all",
    "stop_all",
    "tick",
]


async def start_all() -> None:
    """Start the polling supervisor and the scheduler in this process."""
    await supervisor.start()
    await scheduler.start()


async def stop_all() -> None:
    """Stop the scheduler and the polling supervisor in this process."""
    await scheduler.stop()
    await supervisor.stop()
