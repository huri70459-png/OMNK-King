from dataclasses import dataclass

from .model import Target


@dataclass(frozen=True)
class TargetIdentity:
    argv: tuple[str, ...]
    cwd: str
    pid: int
    port: int
    origin: str

    def as_target(self) -> Target:
        return Target(self.argv, self.cwd, self.pid, self.port, self.origin)


def identity_for_process(argv: tuple[str, ...], cwd: str, pid: int, port: int, origin: str) -> TargetIdentity:
    """Identity is captured from the runner-owned OS process and socket."""
    if pid <= 0 or port <= 0:
        raise ValueError("invalid process identity")
    return TargetIdentity(argv, cwd, pid, port, origin)
