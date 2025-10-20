from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass
class Proxy:
    raw: str

    def as_chrome_arg(self) -> str:
        if "://" in self.raw:
            return self.raw
        return f"http://{self.raw}"


def parse_proxies_file(path: str) -> List[Proxy]:
    p = Path(path)
    if not p.exists():
        return []
    proxies: List[Proxy] = []
    for line in p.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        proxies.append(Proxy(raw=s))
    return proxies


def round_robin(proxies: List[Proxy]) -> Iterator[Optional[Proxy]]:
    if not proxies:
        while True:
            yield None
    else:
        for proxy in itertools.cycle(proxies):
            yield proxy
