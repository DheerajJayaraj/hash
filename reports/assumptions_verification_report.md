# Engineering Assumptions Verification Report (Milestone 5)

## 1. Executive Summary
This report audits the key physical, thermodynamic, and operational assumptions of the **Heat-Linked Roller Belt for Direct Air Capture (DAC)**. We evaluate parameters against peer-reviewed literature, calculate mutual consistency across operating domains, and isolate critical design uncertainties.

---

## 2. Parameter Provenance and Literature Audit

| Parameter | Register Value | Unit | Provenance | Literature Benchmarks & Citations | Engineering Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Air CO2 Concentration** | `0.72` | g/m³ | ASSUMED | Typical ambient: 415–420 ppm (~0.75 g/m³ at 298.15 K, 101.3 kPa). | Valid ambient baseline (~400 ppm dry air). |
| **Sorbent Areal Loading** | `0.3` | kg/m² | ASSUMED | Coated porous polymer / silica substrates: 0.15–0.50 kg/m² (Wurzbacher et al., 2016; Kumar et al., 2020). | Physically plausible coating thickness (~0.3–0.6 mm at 50% porosity). |
| **Composite Areal Loading** | `0.5` | kg/m² | ASSUMED | Substrate (e.g., woven PTFE / fiberglass mesh: 0.2 kg/m²) + sorbent (0.3 kg/m²). | Consistent ($0.5 \ge 0.3$). Total belt mass loop is ~0.178 kg. |
| **Equilibrium Capacity** | `1.0` | mmol/g (mol/kg) | ASSUMED | Amine-functionalized silicas (PEI, Lewatit VP OC 1065): 0.8–2.1 mmol/g at 400 ppm CO2, 25 °C (Choi et al., 2009; Goeppert et al., 2012; Wurzbacher et al., 2012). | Highly credible literature range; conservative relative to peak lab sorbents (up to 2.5 mmol/g). |
| **Uptake Rate** | `0.065` | mmol/g/min | ASSUMED | Initial uptake for amine-functionalized solid DAC sorbents: 0.04–0.12 mmol/g/min (Kulkarni & Sholl, 2012; Wurzbacher et al., 2016). | Realistic rate for thin-bed passive or forced airflow adsorption. |
| **Desorption Heat** | `1.6` | MWh/t CO2 (5.76 MJ/kg) | ASSUMED | Chemisorption reaction enthalpy ($\Delta H_{ads}$): 65–100 kJ/mol (1.48–2.27 MJ/kg CO2). Sensible heating + desorption total: 4.5–7.0 MJ/kg CO2 (1.25–1.94 MWh/t CO2) in optimized systems. | Consistent with amine-CO2 carbamate bond dissociation enthalpy plus typical carrier heat demand. |
| **Hot Roller Temperature** | `378.15` (105 °C) | K | ASSUMED | Amine thermal swing regeneration: 85–110 °C. Above 120 °C, oxidative and thermal degradation of polyamines accelerates severely (Sayari et al., 2012). | Thermally sound target for PEI/amine without steam stripping. |
| **Intermediate Loop Temp** | `338.15` (65 °C) | K | ASSUMED | Sensible heat recovery stage between hot roller (105 °C) and cooling stage (25 °C). Log mean temperature difference ~ 20–30 K. | Physically sound intermediate stage for liquid loop. |
| **Fan Airflow** | `100–200` | m³/h | ASSUMED | Bench duct face area: 0.054 m² ($0.18 \times 0.3$ m). Face velocity: $150 / (3600 \times 0.054) = 0.77$ m/s. Pressure drop: 50–100 Pa. | Highly consistent with low-pressure axial fan curves. |

---

## 3. Mutual Consistency and Thermodynamic Coherence

### A. The "500 W Heater vs 2.8 g/h Capture Rate" Reality Check
A critical observation arising from our cycle simulation is the relationship between bench-scale heater power and capture rate:
- **Bench Scale Prototype**:
  - Heater power: 500 W.
  - Predicted capture rate: 2.39–2.44 g CO2/h ($6.64 \times 10^{-7}$ kg/s).
  - Theoretical minimum reaction heat for 2.4 g CO2/h:
    $$\dot{Q}_{rxn} = 2.4 \times 10^{-3} \text{ kg/h} \times 5.76 \times 10^6 \text{ J/kg} / 3600 = 0.00384 \text{ W}$$
  - Why is a 500 W heater specified for a reaction requiring < 1 W?
    Because the bench system heats a **2.0 kg aluminum/steel roller** with significant conductive, convective, and ambient losses ($U \cdot A \approx 2$ W/K to ambient, $\sim 160$ W steady standby loss at 105 °C, plus contact conductance to the moving belt).
  - Therefore, at bench scale, the **apparent thermal intensity** is dominated by roller thermal mass and standby loss (~205 MWh/t CO2).
  - At production scale, multiple belt layers pass through sealed recovery chambers with continuous counter-current sorbent flow, dropping thermal demand to 1.5–2.0 MWh/t CO2.
  - **Verdict**: The 500 W heater is necessary for rapid thermal ramp-up and overcoming ambient heat losses on a 2 kg metal roller, but must NOT be confused with the intrinsic thermodynamic demand of the sorbent.

### B. Airflow Limit vs Adsorption Kinetics
- Airflow: 150 m³/h at 0.72 g/m³ delivers **108 g CO2/h** to the adsorption chamber.
- Belt exposed sorbent mass: 0.0162 kg.
- Maximum initial uptake capacity: $0.0162 \text{ kg} \times 0.065 \times 10^{-3} \times 60 \text{ mol/s} \times 44.01 \text{ g/mol} = 2.78 \text{ g CO2/h}$.
- Ratio of CO2 delivery to CO2 capture:
  $$\frac{\text{CO2 Fed}}{\text{CO2 Captured}} = \frac{108 \text{ g/h}}{2.4 \text{ g/h}} \approx 45$$
- **Finding**: Capture is **100% kinetics- and sorbent-mass-limited**, not airflow-starved. Even at minimum fan flow (100 m³/h = 72 g CO2/h), airflow delivers >25x more CO2 than the sorbent can adsorb. Fan flow can be reduced to 30–50 m³/h to save blower electrical energy without decreasing capture rate.

### C. Belt Contact Time and Residence
- Loop length: 1.98 m. Nominal speed: 0.002 m/s (2 mm/s). Full cycle time: 990 s (16.5 min).
- Adsorption zone (0.3 m): residence time = $0.3 / 0.002 = 150$ s (2.5 min).
  In 150 s, sorbent with uptake rate $0.065$ mmol/g/min reaches $\approx 0.16$ mmol/g loading (16% of capacity).
- Hot roller contact zone (0.157 m): residence time = $0.157 / 0.002 = 78.5$ s (1.3 min).
  At 105 °C, thermal desorption with $\tau \approx 60$ s releases >70% of adsorbed CO2.

---

## 4. Sensitivity Dominance Hierarchy

From our parametric sweep in `scripts/run_sensitivity_analysis.py`:
1. **Sorbent Uptake Rate ($\pm 33\%$)**: Produces a **$\pm 32.5\%$ change** in capture rate ($1.66 \to 3.21$ g/h). This is the single highest-leverage material parameter.
2. **Heater Power**: Changes roller operating temperature and ramp-up rate, but above 85 °C desorption is already active; excess power simply increases ambient losses and specific energy.
3. **Belt Speed**: Faster speed (4 mm/s) marginally increases capture rate (+1.2%) while increasing sensible cycling loss, indicating 1.5–2.5 mm/s is an optimal operating plateau.
4. **Fluid Loop Recovery Flow**: Higher flow (1.0 L/min) increases recovered heat from the intermediate roller and reduces belt return temperature.
