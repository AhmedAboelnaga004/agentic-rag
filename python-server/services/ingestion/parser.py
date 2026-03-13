from typing import Awaitable, Callable

from ingest import ingest_data
from ingest_llamaparse import ingest_data_llamaparse


IngestCallable = Callable[..., Awaitable[int]]



def resolve_parser(technique: str) -> IngestCallable:
    return ingest_data_llamaparse if technique == "llamaparse" else ingest_data
