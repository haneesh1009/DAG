from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass
class Diagnostic:
    code: str
    message: str
    severity: str = "error"
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class BuildError(Exception):
    def __init__(self, code, message, **context):
        super().__init__(message)
        self.diagnostic = Diagnostic(code, message, context=context)
