"""持久化层测试"""

from __future__ import annotations

import pytest

# 预先导入模型，确保 fixture 执行前表已注册
from kore.storage import models  # noqa: F401
from kore.storage.db import Base


@pytest.fixture
def db_session():
    """为测试创建独立的内存数据库"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 先导入模型注册所有表
    import kore.storage.models  # noqa: F401

    from kore.storage.db import Base

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def repo(db_session):
    from kore.storage.repository import TaskRepository
    return TaskRepository(db_session)


class TestTaskRepository:
    """任务仓储测试"""

    def test_create_task(self, repo, db_session):
        from kore.storage.models import TaskType

        task = repo.create_task(
            name="test-task",
            task_type=TaskType.SHELL,
            config={"command": "echo hello"},
            description="测试任务",
        )
        assert task.id is not None
        assert task.name == "test-task"
        assert task.task_type == TaskType.SHELL

    def test_get_task(self, repo, db_session):
        from kore.storage.models import TaskType

        created = repo.create_task(name="get-test", task_type=TaskType.SHELL)
        task_id = created.id

        fetched = repo.get_task(task_id)
        assert fetched is not None
        assert fetched.name == "get-test"

    def test_get_task_not_found(self, repo, db_session):
        assert repo.get_task(999) is None

    def test_list_tasks(self, repo, db_session):
        from kore.storage.models import TaskType

        repo.create_task(name="a", task_type=TaskType.SHELL)
        repo.create_task(name="b", task_type=TaskType.HTTP)

        all_tasks = repo.list_tasks()
        assert len(all_tasks) == 2

        shell_tasks = repo.list_tasks(task_type=TaskType.SHELL)
        assert len(shell_tasks) == 1
        assert shell_tasks[0].name == "a"

    def test_update_task(self, repo, db_session):
        from kore.storage.models import TaskType

        task = repo.create_task(name="update-test", task_type=TaskType.SHELL)
        updated = repo.update_task(task.id, description="new desc")
        assert updated is not None
        assert updated.description == "new desc"

    def test_delete_task(self, repo, db_session):
        from kore.storage.models import TaskType

        task = repo.create_task(name="delete-test", task_type=TaskType.SHELL)
        task_id = task.id

        assert repo.delete_task(task_id) is True
        assert repo.get_task(task_id) is None

    def test_set_task_status(self, repo, db_session):
        from kore.storage.models import TaskType, TaskStatus

        task = repo.create_task(name="status-test", task_type=TaskType.SHELL)
        updated = repo.set_task_status(task.id, TaskStatus.PAUSED)
        assert updated is not None
        assert updated.status == TaskStatus.PAUSED

    def test_create_and_update_run(self, repo, db_session):
        from kore.storage.models import TaskType, RunStatus

        task = repo.create_task(name="run-test", task_type=TaskType.SHELL)
        run = repo.create_run(task.id, trigger="manual")
        assert run.id is not None
        assert run.status.value == "pending"

        updated = repo.update_run(
            run.id,
            status=RunStatus.SUCCESS,
            stdout="output",
            exit_code=0,
        )
        assert updated is not None
        assert updated.status == RunStatus.SUCCESS
        assert updated.stdout == "output"

    def test_get_task_runs(self, repo, db_session):
        from kore.storage.models import TaskType

        task = repo.create_task(name="runs-test", task_type=TaskType.SHELL)
        repo.create_run(task.id)
        repo.create_run(task.id)

        runs = repo.get_task_runs(task.id)
        assert len(runs) == 2
