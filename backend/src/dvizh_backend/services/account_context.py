from dataclasses import dataclass, field


@dataclass(frozen=True)
class AccountRequestContext:
    token: str = field(repr=False)
    host: str
    origin: str | None
    write_header: str
