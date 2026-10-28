"""Discretized moving sorbent belt model for the roller-belt DAC simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from dac_sim.sorbent import (
    CO2_MOLAR_MASS_KG_MOL,
    SorbentProperties,
    adsorption_rate_mol_kg_s,
    desorption_rate_mol_kg_s,
)


def _require_positive(name: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a positive finite number.")


@dataclass
class BeltSegment:
    """One spatial element of the moving composite sorbent belt."""

    index: int
    position_m: float
    length_m: float
    sorbent_mass_kg: float
    substrate_mass_kg: float
    specific_heat_j_kg_k: float
    temperature_k: float
    loading_mol_kg: float

    @property
    def total_mass_kg(self) -> float:
        return self.sorbent_mass_kg + self.substrate_mass_kg

    @property
    def heat_capacity_j_k(self) -> float:
        return self.total_mass_kg * self.specific_heat_j_kg_k

    @property
    def co2_content_kg(self) -> float:
        return self.sorbent_mass_kg * self.loading_mol_kg * CO2_MOLAR_MASS_KG_MOL


@dataclass(frozen=True)
class BeltZoneLayout:
    """Zone positions along the belt loop [m]."""

    adsorption_start_m: float = 0.0
    adsorption_end_m: float = 0.30
    hot_roller_start_m: float = 0.65
    hot_roller_end_m: float = 0.65 + 0.15708  # 120 deg wrap on 0.15m roller
    recovery_roller_start_m: float = 0.95
    recovery_roller_end_m: float = 0.95 + 0.10472  # 120 deg wrap on 0.10m roller
    cooling_roller_start_m: float = 1.45
    cooling_roller_end_m: float = 1.45 + 0.15708  # 120 deg wrap on 0.15m roller


class DiscretizedBelt:
    """A discretized continuous loop of moving composite sorbent belt."""

    def __init__(
        self,
        loop_length_m: float = 1.98,
        usable_width_m: float = 0.18,
        belt_speed_m_s: float = 0.002,
        sorbent_areal_loading_kg_m2: float = 0.3,
        composite_areal_loading_kg_m2: float = 0.5,
        specific_heat_j_kg_k: float = 1000.0,
        initial_temperature_k: float = 298.15,
        initial_loading_mol_kg: float = 0.05,
        num_segments: int = 66,
        zones: BeltZoneLayout | None = None,
    ) -> None:
        _require_positive("loop_length_m", loop_length_m)
        _require_positive("usable_width_m", usable_width_m)
        _require_positive("belt_speed_m_s", belt_speed_m_s)
        _require_positive("sorbent_areal_loading_kg_m2", sorbent_areal_loading_kg_m2)
        _require_positive("composite_areal_loading_kg_m2", composite_areal_loading_kg_m2)
        _require_positive("specific_heat_j_kg_k", specific_heat_j_kg_k)
        _require_positive("initial_temperature_k", initial_temperature_k)

        if not isinstance(num_segments, int) or num_segments < 10:
            raise ValueError("num_segments must be an integer >= 10.")
        if initial_loading_mol_kg < 0:
            raise ValueError("initial_loading_mol_kg cannot be negative.")
        if composite_areal_loading_kg_m2 < sorbent_areal_loading_kg_m2:
            raise ValueError(
                "composite_areal_loading_kg_m2 must be >= sorbent_areal_loading_kg_m2."
            )

        self.loop_length_m = loop_length_m
        self.usable_width_m = usable_width_m
        self.belt_speed_m_s = belt_speed_m_s
        self.sorbent_areal_loading_kg_m2 = sorbent_areal_loading_kg_m2
        self.composite_areal_loading_kg_m2 = composite_areal_loading_kg_m2
        self.specific_heat_j_kg_k = specific_heat_j_kg_k
        self.num_segments = num_segments
        self.zones = zones if zones is not None else BeltZoneLayout()

        # Geometry and masses
        self.segment_length_m = loop_length_m / num_segments
        segment_area_m2 = self.segment_length_m * usable_width_m
        self.segment_sorbent_mass_kg = segment_area_m2 * sorbent_areal_loading_kg_m2
        total_segment_mass_kg = segment_area_m2 * composite_areal_loading_kg_m2
        self.segment_substrate_mass_kg = total_segment_mass_kg - self.segment_sorbent_mass_kg

        self.segments: list[BeltSegment] = [
            BeltSegment(
                index=i,
                position_m=i * self.segment_length_m,
                length_m=self.segment_length_m,
                sorbent_mass_kg=self.segment_sorbent_mass_kg,
                substrate_mass_kg=self.segment_substrate_mass_kg,
                specific_heat_j_kg_k=specific_heat_j_kg_k,
                temperature_k=initial_temperature_k,
                loading_mol_kg=initial_loading_mol_kg,
            )
            for i in range(num_segments)
        ]

    @classmethod
    def from_assumptions(
        cls,
        assumptions: dict[str, Any],
        num_segments: int = 66,
        initial_temperature_k: float = 298.15,
        initial_loading_mol_kg: float = 0.05,
    ) -> DiscretizedBelt:
        """Instantiate DiscretizedBelt using values from assumptions register."""
        project = assumptions.get("project", {})
        proto = project.get("prototype", {}).get("value", {})

        def _get_f(d: dict, k: str, default: float) -> float:
            v = d.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            return default

        loop_length = _get_f(proto, "nominal_loop_length", 1.98)
        usable_width = _get_f(proto, "usable_belt_width", 0.18)
        belt_speed = _get_f(proto, "nominal_belt_speed", 0.002)

        sorb_loading_entry = project.get("sorbent_areal_loading", {})
        sorb_loading = _get_f(sorb_loading_entry, "value", 0.3)

        comp_loading_entry = project.get("composite_areal_loading", {})
        comp_loading = _get_f(comp_loading_entry, "value", 0.5)

        return cls(
            loop_length_m=loop_length,
            usable_width_m=usable_width,
            belt_speed_m_s=belt_speed,
            sorbent_areal_loading_kg_m2=sorb_loading,
            composite_areal_loading_kg_m2=comp_loading,
            specific_heat_j_kg_k=1000.0,
            initial_temperature_k=initial_temperature_k,
            initial_loading_mol_kg=initial_loading_mol_kg,
            num_segments=num_segments,
        )

    @property
    def total_sorbent_mass_kg(self) -> float:
        return sum(s.sorbent_mass_kg for s in self.segments)

    @property
    def total_co2_content_kg(self) -> float:
        return sum(s.co2_content_kg for s in self.segments)

    @property
    def mean_temperature_k(self) -> float:
        return sum(s.temperature_k for s in self.segments) / len(self.segments)

    @property
    def mean_loading_mol_kg(self) -> float:
        return sum(s.loading_mol_kg for s in self.segments) / len(self.segments)

    def advance_positions(self, dt_s: float) -> None:
        """Advance all segments around the closed loop by belt_speed * dt."""
        displacement = (self.belt_speed_m_s * dt_s) % self.loop_length_m
        for seg in self.segments:
            new_pos = seg.position_m + displacement
            if new_pos >= self.loop_length_m:
                new_pos -= self.loop_length_m
            seg.position_m = new_pos

    def is_in_adsorption_zone(self, position_m: float) -> bool:
        return self.zones.adsorption_start_m <= position_m <= self.zones.adsorption_end_m

    def is_in_regeneration_zone(self, position_m: float) -> bool:
        return self.zones.hot_roller_start_m <= position_m <= self.zones.hot_roller_end_m

    def is_in_recovery_zone(self, position_m: float) -> bool:
        return self.zones.recovery_roller_start_m <= position_m <= self.zones.recovery_roller_end_m

    def is_in_cooling_zone(self, position_m: float) -> bool:
        return self.zones.cooling_roller_start_m <= position_m <= self.zones.cooling_roller_end_m
