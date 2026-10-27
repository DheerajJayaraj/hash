# Heat-Linked Roller-Belt DAC Simulation

## Current milestone: M0

M0 establishes the assumptions register and its validation layer.
It does not yet calculate thermal performance, capture rates, or energy balances.

## Requirements

- Python 3.13
- Dependencies pinned in `requirements.txt`

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Inspect the assumptions register

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -c "from dac_sim.assumptions import load_assumptions; d=load_assumptions('assumptions.yaml'); print('Validated parameters:', len(d['project']))"
```

## Data provenance

- MEASURED: directly supported by recorded experimental data.
- PUBLISHED: from an identified literature source; verify before citing.
- ASSUMED: project input or regression target not established as a measurement.

Every parameter entry has a value, unit, provenance tag, source, and range.
A null range means a numeric range has not yet been defined; it is not proof
that the value is physically valid.

All numerical results from later simulation modules must report uncertainty
and key assumptions.
