from collections.abc import Callable, Iterable
from dataclasses import dataclass

import httpx

from app.crawlers.base import JobSource
from app.crawlers.sources.himalayas import HimalayasJobSource


JobSourceFactory = Callable[[httpx.AsyncClient], JobSource]


@dataclass(frozen=True, slots=True)
class JobSourceDefinition:
    name: str
    factory: JobSourceFactory
    max_limit: int = 20

    def __post_init__(self) -> None:
        normalized_name = self.name.strip().casefold()

        if not normalized_name:
            raise ValueError("Job source name must not be empty.")

        if self.max_limit < 1:
            raise ValueError("Job source max_limit must be greater than zero.")

        object.__setattr__(self, "name", normalized_name)

    def create(self, client: httpx.AsyncClient) -> JobSource:
        source = self.factory(client)

        if not isinstance(source, JobSource):
            raise TypeError(
                f"Source {self.name!r} does not implement JobSource."
            )

        if source.source_name.casefold() != self.name:
            raise ValueError(
                "Registered source name does not match adapter source_name: "
                f"{self.name!r} != {source.source_name!r}."
            )

        return source


class JobSourceRegistry:
    def __init__(self, definitions: Iterable[JobSourceDefinition]) -> None:
        self._definitions: dict[str, JobSourceDefinition] = {}

        for definition in definitions:
            if definition.name in self._definitions:
                raise ValueError(
                    f"Duplicate job source: {definition.name}"
                )

            self._definitions[definition.name] = definition

        if not self._definitions:
            raise ValueError(
                "At least one job source must be registered."
            )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def get(self, source_name: str) -> JobSourceDefinition:
        normalized_name = source_name.strip().casefold()

        try:
            return self._definitions[normalized_name]
        except KeyError as error:
            supported_sources = ", ".join(self.names)

            raise ValueError(
                f"Unsupported source: {source_name}. "
                f"Supported sources: {supported_sources}"
            ) from error

    def create(self, source_name: str, client: httpx.AsyncClient) -> JobSource:
        definition = self.get(source_name)

        return definition.create(client)


DEFAULT_JOB_SOURCE_REGISTRY = JobSourceRegistry(
    definitions=[
        JobSourceDefinition(
            name="himalayas",
            factory=HimalayasJobSource,
            max_limit=20,
        ),
    ]
)