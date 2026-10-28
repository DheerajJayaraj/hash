# Physical Prototype Testing and Readiness Plan (Milestone 7)

## 1. Executive Summary
This document provides a practical, instrumented test plan to validate the **Heat-Linked Roller Belt for Direct Air Capture** experimental bench prototype against simulation predictions. It defines sensor selections, mass/energy balance measurement protocols, test sequences, criteria for model validation, and safety mitigations.

> [!CAUTION]
> The bench prototype incorporates moving continuous belts, a 500 W electric heater (105 °C surface temperatures), fluid circulation, and sealed desorbed CO2 gas collection. Experimental testing must adhere to strict electrical, thermal, and mechanical safety procedures.

---

## 2. Instrumentation and Sensor Architecture

To close mass and energy balances experimentally, the bench must be equipped with the following calibrated instrumentation:

```
[ Ambient Air Inflow ]
       │
       ▼
 [ Fan & Flowmeter ]  ──> [ NDIR CO2 Sensor #1 (0-2000 ppm) + Temp/RH ]
                                │
                                ▼
                   ┌─────────────────────────────┐
                   │   Adsorption Duct (0.3m)    │ ─── Moving Sorbent Belt
                   └─────────────────────────────┘
                                │
                                ▼
             [ NDIR CO2 Sensor #2 (0-2000 ppm) + Exhaust Velocity Grid ]
                                │
                                ▼
                       [ Exhaust to Room ]

┌────────────────────────────────────────────────────────────────────────┐
│                        Regeneration Enclosure                          │
│                                                                        │
│   [ 500W Heated Roller (Pt100 RTD) ] ──> Sorbent Desorption Contact    │
│   [ Sorbent Belt Surface (IR Pyrometer) ]                              │
│   [ Fluid Loop Heat Exchanger (Pt100 In/Out + Turbine Flowmeter) ]     │
│   [ NDIR High-Range CO2 Sensor #3 (0-100% CO2) + Mass Flow Meter ]     │
│   [ Chilled Condensate Trap (Moisture knockout) ]                      │
└────────────────────────────────────────────────────────────────────────┘
```

### Sensor Specifications
| Measurement | Instrument Type | Range | Accuracy | Target Parameter |
| :--- | :--- | :--- | :--- | :--- |
| **Inlet Air CO2** | Dual-beam NDIR | 0–2000 ppm | $\pm 20$ ppm | $C_{air, in}$ ($0.72$ g/m³) |
| **Outlet Air CO2** | Dual-beam NDIR | 0–2000 ppm | $\pm 20$ ppm | $C_{air, out}$ (untreated CO2) |
| **Airflow Rate** | Pitot array / Hot wire | 50–250 m³/h | $\pm 3\%$ | $\dot{V}_{air}$ ($150$ m³/h) |
| **Desorption CO2** | Thermal conductivity / High NDIR | 0–100% | $\pm 1\%$ | Desorption gas purity |
| **Desorption Gas Flow** | Thermal Mass Flow Meter (MFC) | 0–2.0 L/min | $\pm 1\%$ | $\dot{m}_{CO2, released}$ |
| **Hot Roller Temp** | Embedded 4-wire Pt100 RTD | 0–150 °C | $\pm 0.1$ °C | $T_{hot}$ ($105$ °C) |
| **Belt Surface Temp** | Calibrated IR Pyrometer ($\varepsilon=0.92$) | 0–120 °C | $\pm 0.5$ °C | $T_{belt}$ |
| **Fluid Loop Temp** | Immersion RTD pair ($T_{in}, T_{out}$) | 0–100 °C | $\pm 0.05$ °C | $\Delta T_{fluid}$ |
| **Fluid Flow Rate** | Low-flow turbine / magnetic | 0.2–2.0 L/min | $\pm 1.5\%$ | $\dot{m}_{fluid}$ |
| **Heater Electrical Power** | True-RMS digital power transducer | 0–1000 W | $\pm 0.5\%$ | $P_{heater}$ ($500$ W) |

---

## 3. Step-by-Step Test Sequence

### Phase 1: Mechanical and Thermal Shakedown (Zero Sorbent / Dry Belt)
1. **Belt Tracking & Drive Check**:
   - Run drive motor at 1, 2, and 4 mm/s for 30 minutes without heating or airflow.
   - Verify belt lateral drift is $< 2$ mm over 30 min. Check tensioner stability.
2. **Thermal Response and Loss Calibration**:
   - Power heater at 500 W with stationary belt. Record $T_{hot}(t)$ to determine roller thermal capacity ($m c_p \approx 1000$ J/K).
   - Once at 105 °C steady state, determine ambient loss conductance:
     $$G_{amb, hot} = \frac{P_{heater, steady}}{T_{hot, steady} - T_{ambient}}$$
   - Engage fluid loop at 0.5 L/min and calibrate heat recovery conductance ($G_{fluid}$).

### Phase 2: Flow and Aerodynamic Baselines
1. **Airflow Characterization**:
   - Step fan speed across 30%, 50%, 80%, 100% PWM.
   - Measure face velocity across the 0.054 m² duct; verify duct velocity profile uniformity ($> 90\%$).
   - Record duct differential pressure ($\Delta P \approx 50–100$ Pa).
2. **CO2 Background Stability**:
   - Run room air through duct for 15 minutes. Verify NDIR #1 and NDIR #2 match within $\pm 10$ ppm under zero capture.

### Phase 3: Live DAC Cycle Testing
1. **Continuous Capture Run (3 Cycles / ~50 minutes)**:
   - Configure: belt speed = 2.0 mm/s, fan = 150 m³/h, heater setpoint = 105 °C, fluid flow = 0.5 L/min.
   - Continuous logging at 1 Hz across all instruments.
   - Compute instantaneous capture rate from differential:
     $$\dot{m}_{captured}(t) = \dot{V}_{air} \cdot [C_{CO2, in}(t) - C_{CO2, out}(t)]$$
   - Measure desorbed gas flow and purity in the desorption chamber.
2. **Mass and Energy Closure**:
   - Calculate cumulative CO2 captured in air vs CO2 desorbed.
   - Validate against model predictions ($2.4 \pm 0.4$ g/h).

---

## 4. Criteria for Comparing Experiment against Simulation

The simulation is considered physically validated if experimental observations meet the following quantitative benchmarks:

| Criterion | Target Tolerance | Metric / Method |
| :--- | :--- | :--- |
| **Air Capture Rate** | $\pm 20\%$ of simulation | Experimental $\Delta C_{CO2} \cdot \dot{V}_{air}$ vs simulated $2.39$ g/h. |
| **Regeneration Desorption Rate** | $\pm 20\%$ of simulation | Cumulative gas collected in desorption chamber. |
| **Roller Temperature Trajectory** | $\pm 3.0$ K root-mean-square | Transient heating curve $T_{hot}(t)$ from 25 to 105 °C. |
| **CO2 Mass Balance Closure** | $< 10\%$ residual | $|m_{captured} - m_{released} - \Delta m_{sorbent}| / m_{captured} < 0.10$. |
| **Energy Balance Closure** | $< 10\%$ residual | Thermal input vs ($m c_p \Delta T + \Delta H_{desorp} + Q_{losses}$). |

---

## 5. Hazard Analysis and Safety Protocol

1. **Thermal Burn Hazard**:
   - Hot roller and belt reach 105 °C.
   - Enclose regeneration chamber with transparent polycarbonate / acrylic guarding.
   - Implement hardware over-temperature cutoff switch (bimetallic thermostat set to 120 °C) independent of software control.
2. **Mechanical Pinch Points**:
   - Rollers rotating at ~0.25 rpm present finger-entrapment risks at belt nip points.
   - Install nip guards and an emergency stop button that cuts motor and heater power simultaneously.
3. **Electrical Safety**:
   - 500 W cartridge heaters operating at 110/230 VAC require dedicated RCD/GFCI protection and chassis grounding.
4. **Gas Leakage / Air Ingress**:
   - Desorbed CO2 is an asphyxiant at high concentrations (> 5% in unventilated spaces).
   - Ensure room ventilation is $> 4$ air changes/hour; install ambient room CO2 monitor with audible alarm set at 5000 ppm (OSHA PEL).
