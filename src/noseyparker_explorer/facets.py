from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

@dataclass(frozen=True, order=True, repr=True, slots=True)
class FacetDefinition:
    """
    The definition of a facet.
    This includes all the information needed to display a facet value in the UI,
    as well as all that is needed to focus on a facet in the `NoseyParkerDatastore`.
    """

    name: str           # human-readable name for the facet, to be used in labels
    column: str         # the column in `matches` to facet on

    sort_order: Literal['name', 'count'] = 'name'
    sort_reverse: bool = False

    # def sort_key(self) -> Callable[[tuple[FacetValue, FacetMetadata]], Any]:
    #     if self.sort_order == 'name':
    #         return lambda vm: vm[0].definition.name
    #     elif self.sort_order == 'num_matches':
    #         return lambda vm: (vm[1].num_matches, vm[0].definition.name)


@dataclass(order=True, repr=True, slots=True)
class FacetMetadata:
    count: int  # the number of applicable items

@dataclass(frozen=True, order=True, repr=True, slots=True)
class FacetValue:
    definition: FacetDefinition     # the sql database column this facet applies to
    value: None | str | bytes       # the value for `definition.value_column`
