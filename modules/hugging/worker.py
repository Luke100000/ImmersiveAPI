import asyncio
import queue
import threading
from dataclasses import dataclass, field
from typing import Any


class Worker:
    def __init__(self, q: queue.Queue):
        self.task_queue = q
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run)
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                item = self.task_queue.get(timeout=1)
                item.item()
            except queue.Empty:
                pass

    def submit_task(self, task, priority):
        self.task_queue.put((priority, task))

    def stop(self):
        self.stop_event.set()
        self.thread.join()


@dataclass(order=True)
class PrioritizedItem:
    priority: int
    item: Any = field(compare=False)


class Executor:
    def __init__(self, max_workers: int):
        self.queue = queue.PriorityQueue()
        self.workers = [Worker(self.queue) for _ in range(max_workers)]

    def submit(self, priority: int, func, *args, **kwargs):
        future = asyncio.get_running_loop().create_future()
        self.queue.put(
            PrioritizedItem(priority, lambda: future.set_result(func(*args, **kwargs)))
        )
        return future

    def shutdown(self):
        for worker in self.workers:
            worker.stop()
