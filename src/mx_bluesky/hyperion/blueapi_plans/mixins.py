from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, Field


class MultiXtalSelection(BaseModel):
    name: str
    ignore_xtal_not_found: bool = False


class TopNByMaxCountSelection(MultiXtalSelection):
    name: Literal["TopNByMaxCount"] = "TopNByMaxCount"  #  pyright: ignore [reportIncompatibleVariableOverride]
    n: int


class TopNByMaxCountForEachSampleSelection(MultiXtalSelection):
    name: Literal["TopNByMaxCountForEachSample"] = "TopNByMaxCountForEachSample"  #  pyright: ignore [reportIncompatibleVariableOverride]
    n: int


class WithCentreSelection(BaseModel):
    select_centres: TopNByMaxCountSelection | TopNByMaxCountForEachSampleSelection = (
        Field(discriminator="name", default=TopNByMaxCountSelection(n=1))
    )

    @property
    def selection_params(self) -> MultiXtalSelection:
        """A helper property because pydantic does not allow polymorphism with base classes
        # only type unions"""
        cast1 = cast(MultiXtalSelection, self.select_centres)
        return cast1
