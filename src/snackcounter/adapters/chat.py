"""Simulated chat tool. The real one would send DMs with buttons ("I'll take it")."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    to: str          # user id or "channel:<office>" / "managers:<office>"
    kind: str        # offer | taken | reassigned | escalation | reimbursed | rejected ...
    refill_id: int
    text: str = ""


class FakeChat:
    def __init__(self):
        self.messages: list[Message] = []

    def send(self, to: str, kind: str, refill_id: int, text: str = "") -> None:
        self.messages.append(Message(to, kind, refill_id, text))

    def of_kind(self, kind: str) -> list[Message]:
        return [m for m in self.messages if m.kind == kind]
