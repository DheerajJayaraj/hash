# Downstream Methanol Production Feasibility and Integration Assessment (Milestone 6)

## 1. Executive Summary
Methanol ($\text{CH}_3\text{OH}$) synthesis from Direct Air Capture (DAC) CO2 represents an e-fuel and chemical feedstock pathway. This report evaluates the thermodynamic stoichiometry, hydrogen demand, gas conditioning constraints, reactor conditions, and integration interfaces with the Heat-Linked Roller Belt system.

> [!IMPORTANT]
> Methanol cannot be produced simply because a DAC simulation reports captured CO2. CO2 is a fully oxidized carbon molecule ($\Delta G^\circ_f = -394.4$ kJ/mol); synthesizing methanol requires high-energy green hydrogen ($\text{H}_2$), high pressure (50–80 bar), heterogeneous catalysis ($\text{Cu/ZnO/Al}_2\text{O}_3$), and strict gas purification.

---

## 2. Reaction Thermodynamics and Stoichiometry

Direct catalytic hydrogenation of CO2 proceeds via the exothermic reaction:
$$\text{CO}_2 + 3 \text{H}_2 \rightleftharpoons \text{CH}_3\text{OH} + \text{H}_2\text{O} \quad (\Delta H^\circ_{298} = -49.5 \text{ kJ/mol}, \; \Delta G^\circ_{298} = +3.5 \text{ kJ/mol})$$

Competitively accompanied by the endothermic Reverse Water-Gas Shift (RWGS) reaction:
$$\text{CO}_2 + \text{H}_2 \rightleftharpoons \text{CO} + \text{H}_2\text{O} \quad (\Delta H^\circ_{298} = +41.2 \text{ kJ/mol})$$

### Stoichiometric Mass Ratios
| Component | Formula | Molar Mass | Mass per kg Methanol |
| :--- | :--- | :--- | :--- |
| **Methanol (Product)** | $\text{CH}_3\text{OH}$ | 32.042 g/mol | 1.000 kg |
| **CO2 Required (Theoretical)** | $\text{CO}_2$ | 44.010 g/mol | **1.3735 kg** ($1.375$ in assumptions) |
| **H2 Required (Theoretical)** | $\text{H}_2$ | 2.016 g/mol | **0.1887 kg** |
| **Water Byproduct** | $\text{H}_2\text{O}$ | 18.015 g/mol | **0.5622 kg** |

At 95% overall synthesis efficiency with unreacted syngas recycle:
- **Actual CO2 demand**: **1.446 kg CO2 / kg methanol**.
- **Actual H2 demand**: **0.198 kg H2 / kg methanol**.

---

## 3. Hydrogen Supply and Electrical Energy Balance

Green hydrogen is produced via water electrolysis:
$$2 \text{H}_2\text{O} \xrightarrow{\text{electricity}} 2 \text{H}_2 + \text{O}_2$$
- Lower Heating Value (LHV) of H2: **120.0 MJ/kg (33.33 kWh/kg)**.
- High Heating Value (HHV) of H2: **141.8 MJ/kg (39.39 kWh/kg)**.
- Modern PEM or Alkaline electrolyzer efficiency: **65–70% LHV** (50–55 kWh/kg H2).

### Energy Demand Breakdown per Ton of Methanol
1. **Electrolysis Power**:
   $$0.1887 \text{ t H2} \times 52.0 \text{ MWh/t H2} = \mathbf{9.81 \text{ MWh/t methanol}}$$
   *(Exact match to `assumptions.yaml: electrolysis_energy: 9.8 MWh/t_methanol`)*.
2. **Compression Work**:
   Compressing CO2 (from 1 to 60 bar) and H2 (from 30 to 60 bar) requires **~0.15–0.25 MWh/t methanol**.
3. **Distillation and Refining**:
   Separating crude methanol (64 wt% methanol, 36 wt% water) to chemical-grade (AA) methanol requires **~0.6–0.8 MWh thermal/t methanol**.
4. **Total System Electrical Demand**:
   **~10.2–10.6 MWh electrical per ton of e-methanol**.

---

## 4. Thermal Integration with DAC System

The methanol synthesis reaction is strongly exothermic ($\Delta H = -49.5$ kJ/mol CH3OH = $-1.545$ MJ/kg CH3OH).
- Reactor operating temperature: **230–260 °C**.
- High-grade heat released: **~0.297 MWh thermal / ton CO2 reacted**.
- Heat Recovery Potential:
  Steam generated at 10–15 bar (180–200 °C) from the reactor cooling jacket can be directly reused as the **heat source for the DAC hot roller or sorbent regeneration**.
  At 60% recovery: **0.18–0.31 MWh thermal / ton CO2** can offset DAC heating demand.
  *(This validates the `reactor_heat_reuse: 0.31 MWh/t_CO2` parameter in `assumptions.yaml`)*.

---

## 5. Gas Conditioning and Purity Requirements

Direct air capture exhaust contains contaminants that poison downstream copper-zinc catalysts ($\text{Cu/ZnO/Al}_2\text{O}_3$):
- **Moisture**: DAC regeneration gas typically contains 5–30% water vapor. Must be knocked out via condenser / chiller to $< 0.1\%$ before compression.
- **Oxygen ($\text{O}_2$)**: DAC regeneration can entrain residual air (0.1–1.0% O2). Oxygen oxidizes the active copper sites ($\text{Cu}^0 / \text{Cu}^+ \to \text{Cu}^{2+}$) causing irreversible sintering. Catalytic de-oxo polishing is required ($\text{O}_2 < 1$ ppm).
- **Sulfur ($\text{SO}_2, \text{H}_2\text{S}$)**: Poison threshold $< 0.05$ ppm. Desulfurization guard bed required.
- **Nitrogen ($\text{N}_2$)**: Inert, but accumulates in syngas recycle loop; purge stream required.

---

## 6. Sizing and Bench-Scale Interface Interface Contract

For the bench prototype capturing **2.4 g CO2/h**:
- **CO2 Supply Rate**: $2.4 \times 10^{-3}$ kg/h ($0.0545$ mol CO2/h).
- **H2 Supply Rate**: $0.33 \text{ g H2/h} = 0.164 \text{ mol/h} = 3.67 \text{ NL/h}$.
- **Electrolysis Power**: **~17.2 W continuous**.
- **Methanol Yield**: **1.66 g CH3OH/h (2.1 mL/h)**.
- **Water Byproduct**: **0.93 g H2O/h (0.93 mL/h)**.
- **Exothermic Heat Output**: **~0.75 W**.

### Recommendation
At the 2.4 g/h bench scale, physical chemical synthesis in a high-pressure (60 bar) heated micro-reactor is impractical and poses high hydrogen flammability risks. CO2 captured from the bench DAC belt should be collected, quantified, and qualified via gas chromatography / FTIR rather than fed to an uncertified high-pressure reactor. Physical methanol synthesis should be decoupled to an engineered skid at scale-up ($\ge 1$ kg CO2/h).
