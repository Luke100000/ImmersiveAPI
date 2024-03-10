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
                try:
                    item.item()
                except Exception as e:
                    print(e)
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

        def task():
            try:
                future.set_result(func(*args, **kwargs))
            except Exception as e:
                future.set_exception(e)

        self.queue.put(PrioritizedItem(priority, task))
        return future

    def shutdown(self):
        for worker in self.workers:
            worker.stop()


_worker = None


def set_primary_executor(executor: Executor):
    global _worker
    _worker = executor


def get_primary_executor():
    global _worker
    return _worker
