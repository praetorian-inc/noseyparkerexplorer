from __future__ import annotations

from .facets import FacetValue


class Filters:
    """
    Represents the state of user-applied filters on the findings.
    """

    def __init__(self, *, min_score: None | float) -> None:
        self._facets: set[FacetValue] = set()
        self._min_score: float = max(0.0, min_score or 0.0)

    @property
    def facets(self) -> set[FacetValue]:
        return self._facets

    @property
    def min_score(self) -> float:
        return self._min_score

    def set_min_score(self, min_score: float) -> bool:
        """
        Sets the minimum score to the given value.
        Returns true if the minimum score was changed.
        """
        min_score = max(0.0, min_score)

        if min_score != self._min_score:
            self._min_score = min_score
            return True

        return False

    def select_facet_value(self, facet_value: FacetValue) -> bool:
        """
        Select the given facet value.
        Returns true if the filters were modified.
        """
        if facet_value in self._facets:
            return False

        self._facets.add(facet_value)
        return True

    def deselect_facet_value(self, facet_value: FacetValue) -> bool:
        """
        Deselect the given facet value.
        Returns true if the filters were modified.
        """
        if facet_value not in self._facets:
            return False

        self._facets.remove(facet_value)
        return True

    def clear(self) -> bool:
        """
        Clear all filters.
        Returns true if the filters were modified.
        """
        if self._facets:
            self._facets.clear()
            return True
        return False
