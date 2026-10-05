"""
Technical proposal for extending Olympus to support multiple projects with:
- Context isolation
- Independent execution
- Separate persistence

Declarative schema defining core abstractions and relationships.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from enum import Enum

class IsolationMode(str, Enum):
    """Isolation mechanisms for project contexts."""
    PROCESS = "process"
    THREAD = "thread"
    CONTAINER = "container"

class ExecutionModel(str, Enum):
    """Execution paradigms for project workloads."""
    SYNC = "sync"
    ASYNC = "async"
    FUNCTIONAL = "functional"
    DECLARATIVE = "declarative"

class PersistenceStrategy(str, Enum):
    """Persistence backends for project data."""
    DOCUMENT_DB = "document_db"
    RELATIONAL_DB = "relational_db"
    KEY_VALUE = "key_value"
    EVENT_STORE = "event_store"
    CUSTOM = "custom"

@dataclass
class ProjectIdentity:
    """Immutable identifier for a project within Olympus."""
    id: str
    name: str
    version: str = "1.0.0"
    tags: dict[str, str] = field(default_factory=dict)

@dataclass
class ContextConfig:
    """Configuration describing isolation characteristics."""
    mode: IsolationMode = IsolationMode.PROCESS
    shared_resources: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)

@dataclass
class ExecutionConfig:
    """Configuration describing execution behavior."""
    model: ExecutionModel = ExecutionModel.ASYNC
    timeout_seconds: int = 300
    max_concurrent_jobs: int = 1

@dataclass
class PersistenceConfig:
    """Configuration describing data storage behavior."""
    strategy: PersistenceStrategy = PersistenceStrategy.KEY_VALUE
    connection_uri: str = ""
    options: dict[str, str] = field(default_factory=dict)

@dataclass
class ProjectDescriptor:
    """High‑level description of a supported project in Olympus."""
    identity: ProjectIdentity
    context: ContextConfig = field(default_factory=ContextConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)

@runtime_checkable
class ContextProvider(Protocol):
    """Protocol for a context that can be isolated per project."""
    def isolate(self, project_id: str) -> None: ...
    def release(self, project_id: str) -> None: ...

@runtime_checkable
class Executor(Protocol):
    """Protocol for independent execution environments."""
    def run(self, payload: object) -> object: ...
    def shutdown(self) -> None: ...

@runtime_checkable
class PersistenceLayer(Protocol):
    """Protocol for project‑specific persistence."""
    def store(self, key: str, data: object) -> None: ...
    def retrieve(self, key: str) -> object | None: ...
    def clear(self) -> None: ...

@dataclass
class ProjectRuntime:
    """Runtime components instantiated for a single project."""
    context: ContextProvider | None = None
    executor: Executor | None = None
    persistence: PersistenceLayer | None = None

@dataclass
class MultiProjectOrchestrator:
    """Orchestrator that manages isolation, execution, and persistence per project."""
    projects: dict[str, ProjectDescriptor] = field(default_factory=dict)
    runtimes: dict[str, ProjectRuntime] = field(default_factory=dict)

    def register(self, descriptor: ProjectDescriptor) -> None:
        """Declare a new project for management."""
        self.projects[descriptor.identity.id] = descriptor

    def bootstrap(self, project_id: str) -> ProjectRuntime:
        """Provision isolated runtime for the requested project."""
        if project_id not in self.projects:
            raise ValueError(f"Unknown project: {project_id}")
        descriptor = self.projects[project_id]
        runtime = ProjectRuntime()
        # Declarative mapping of descriptor to concrete providers omitted.
        return runtime

    def shutdown(self, project_id: str) -> None:
        """Clean up isolated runtime for the project."""
        runtime = self.runtimes.pop(project_id, None)
        if runtime and runtime.executor:
            runtime.executor.shutdown()
__end__
