import logging

from uuid import UUID
from obi_one.types import TaskType

from pydantic import BaseModel

from utils import run_cloud_task


L = logging.getLogger(__name__)


class Task(BaseModel):
    config_id: UUID
    task_type: TaskType


subdomains = [
    # ("aws", "cell_a"),
    ("azure", "cell_b")
]


tasks = [
    Task(
        config_id=UUID("65235f18-c18e-40e6-8c16-b1fdff9da6ce"),
        task_type=TaskType.ion_channel_model_simulation_execution,
    )
]


def main():
    for task in tasks:
        for vendor, subdomain in subdomains:
            try:
                print(f"{task.task_type}: {vendor} {subdomain} Launched")
                run_cloud_task(
                    task_type=task.task_type,
                    config_id=task.config_id,
                    subdomain=subdomain,
                    environment="local",
                )
                print(f"{task.task_type}: {vendor} {subdomain} Success")
            except Exception:
                L.exception("Task failed.")
                print(f"{task.task_type}: {vendor} {subdomain} Failure")


if __name__ == "__main__":
    main()
