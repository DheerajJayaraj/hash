"""Tests for downstream methanol synthesis assessment."""

import pytest

from dac_sim.methanol import (
    MethanolProcessConfig,
    evaluate_methanol_production,
    CO2_MOLAR_MASS_G_MOL,
    METHANOL_MOLAR_MASS_G_MOL,
)


def test_methanol_stoichiometry_and_mass_balance():
    # 1.3735 kg CO2 per kg methanol at 100% conversion
    ideal_cfg = MethanolProcessConfig(overall_conversion_efficiency=1.0)
    result = evaluate_methanol_production(1.373494, ideal_cfg)

    assert result.methanol_produced_kg_h == pytest.approx(1.0, rel=1e-3)
    # 3 moles H2 (6.048 g) per mole methanol (32.042 g) -> 0.1887 kg H2 / kg methanol
    assert result.h2_demand_kg_h == pytest.approx(6.048 / 32.042, rel=1e-3)
    # 1 mole H2O (18.015 g) per mole methanol (32.042 g) -> 0.5622 kg H2O / kg methanol
    assert result.water_byproduct_kg_h == pytest.approx(18.015 / 32.042, rel=1e-3)

    # Mass conservation: CO2 + H2 = Methanol + H2O
    total_in = result.co2_feed_kg_h + result.h2_demand_kg_h
    total_out = result.methanol_produced_kg_h + result.water_byproduct_kg_h
    assert total_in == pytest.approx(total_out, rel=1e-4)


def test_electrolysis_and_thermal_energy_scale():
    # Evaluate at 1 ton CO2 / h feed
    result = evaluate_methanol_production(1000.0)

    # Standard electrolysis electricity demand is 9-11 MWh / t methanol
    assert 8.0 < result.electrolysis_energy_mwh_t_methanol < 12.0
    # Methanol produced ~ 690-700 kg/h
    assert 650.0 < result.methanol_produced_kg_h < 750.0

    # Exothermic reaction heat is released and recoverable
    assert result.exothermic_heat_generated_kw > 0
    assert result.recoverable_heat_kw > 0
    # Total reaction heat generated is ~0.297 MWh/t CO2 (~0.31 MWh/t CO2 in assumptions register)
    heat_generated_mwh_t_co2 = (result.exothermic_heat_generated_kw / 1000.0) / (result.co2_feed_kg_h / 1000.0)
    assert 0.25 < heat_generated_mwh_t_co2 < 0.35
    assert 0.15 < result.recoverable_heat_mwh_t_co2 < 0.35



def test_config_validation():
    with pytest.raises(ValueError):
        MethanolProcessConfig(operating_pressure_bar=-10.0)
    with pytest.raises(ValueError):
        MethanolProcessConfig(overall_conversion_efficiency=1.5)
    with pytest.raises(ValueError):
        evaluate_methanol_production(0.0)
