"""Flow for electrode analysis."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jobflow import Flow, Maker
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher

from atomate2.common.jobs.electrode import get_stable_inserted_structure

if TYPE_CHECKING:
    from pymatgen.alchemy import ElementLike
    from pymatgen.core.structure import Structure
    from pymatgen.io.vasp.outputs import VolumetricData

logger = logging.getLogger(__name__)

__author__ = "Jimmy Shen"
__email__ = "jmmshn@gmail.com"


@dataclass
class ElectrodeInsertionMaker(Maker, ABC):
    """Attempt ion insertion into a structure.

    The basic unit for cation insertion is:
        [get_stable_inserted_structure]:
            (static) -> (chgcar analysis) ->
            N x (relax) -> (return best structure)

    The workflow is:
        [relax structure]
        [get_stable_inserted_structure]
        [get_stable_inserted_structure]
        [get_stable_inserted_structure]
        ... until the insertion is no longer topotactic.

    This workflow requires the users to provide the following functions:
        self.get_charge_density(task_doc: TaskDoc):
            Get the charge density of a TaskDoc output from a calculation.
        self.update_static_maker():
            Ensure that the static maker will store the desired data.

    Attributes
    ----------
    name: str
        The name of the flow created by this maker.
    relax_maker: RelaxMaker
        A maker to perform relaxation calculations.
    bulk_relax_maker: Maker
        A separate maker to perform the first bulk relaxation calculation.
        If None, the relax_maker will be used.
    static_maker: Maker
        A maker to perform static calculations.
    structure_matcher: StructureMatcher
        The structure matcher to use to determine if additional insertion is needed.
    """

    relax_maker: Maker
    static_maker: Maker
    bulk_relax_maker: Maker | None = None
    name: str = "ion insertion"
    structure_matcher: StructureMatcher = field(
        default_factory=lambda: StructureMatcher(
            comparator=ElementComparator(),
        )
    )

    def __post_init__(self) -> None:
        """Ensure that the static maker will store the desired data."""
        self.update_static_maker()

    def make(
        self,
        structure: Structure,
        inserted_element: ElementLike,
        n_steps: int | None,
        insertions_per_step: int = 4,
    ) -> Flow:
        """Make the flow.

        Parameters
        ----------
        structure:
            Structure to insert ion into.
        inserted_species:
            Species to insert.
        n_steps: int
            The maximum number of sequential insertion steps to attempt.
        insertions_per_step: int
            The maximum number of ion insertion sites to attempt.

        Returns
        -------
            Flow for ion insertion.
        """
        # First relax the structure
        if self.bulk_relax_maker:
            relax = self.bulk_relax_maker.make(structure)
        else:
            relax = self.relax_maker.make(structure)
        # add ignored_species to the structure matcher
        sm = _add_ignored_species(self.structure_matcher, inserted_element)
        # Get the inserted structure
        inserted_structure = get_stable_inserted_structure(
            structure=relax.output.structure,
            inserted_element=inserted_element,
            structure_matcher=sm,
            static_maker=self.static_maker,
            relax_maker=self.relax_maker,
            get_charge_density=self.get_charge_density,
            n_steps=n_steps,
            insertions_per_step=insertions_per_step,
        )
        return Flow([relax, inserted_structure])

    @abstractmethod
    def get_charge_density(self, prev_dir) -> VolumetricData:
        """Get the charge density of a structure.

        Parameters
        ----------
        prev_dir:
            The previous directory where the static calculation was performed.

        Returns
        -------
            The charge density.
        """

    @abstractmethod
    def update_static_maker(self) -> None:
        """Ensure that the static maker will store the desired data."""


def _add_ignored_species(
    structure_matcher: StructureMatcher, species: ElementLike
) -> StructureMatcher:
    """Add an ignored species to a structure matcher."""
    sm_dict = structure_matcher.as_dict()
    ignored_species = set(sm_dict.get("ignored_species", set()))
    ignored_species.add(str(species))
    sm_dict["ignored_species"] = list(ignored_species)
    return StructureMatcher.from_dict(sm_dict)
