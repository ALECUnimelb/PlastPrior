"""Reproduce frozen Pov/LRTP calculations and isolate unverified chemical identities.

The numerical kernel preserves the historical operation order and environmental
constants. Agreement with archived outputs is distinct from independent
validation against an identified release of the official OECD workbook.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import json
import math
from pathlib import Path
import platform
from typing import Any, Optional

import pandas as pd

from .inputs import _file_hash

LOGKOW_COL = "LogP model (Meylan-Kowwin) | Predicted LogP"
LOGKOW_ASSESSMENT_COL = "LogP model (Meylan-Kowwin) | Assessment"
LOGKOW_ADI_COL = "LogP model (Meylan-Kowwin) | ADI"

HLAIR_COL = "Air Half-Life (IRFMN-CORAL) | Predicted Air Half-Life [hours]"
HLAIR_ASSESSMENT_COL = "Air Half-Life (IRFMN-CORAL) | Assessment"
HLAIR_ADI_COL = "Air Half-Life (IRFMN-CORAL) | ADI"

HLWATER_DAYS_COL = "Persistence (water) quantitative model (IRFMN) | Predicted HL [days]"
HLWATER_ASSESSMENT_COL = "Persistence (water) quantitative model (IRFMN) | Assessment"
HLWATER_ADI_COL = "Persistence (water) quantitative model (IRFMN) | ADI"

HLSOIL_DAYS_COL = "Persistence (soil) quantitative model (IRFMN) | Predicted HL [days]"
HLSOIL_ASSESSMENT_COL = "Persistence (soil) quantitative model (IRFMN) | Assessment"
HLSOIL_ADI_COL = "Persistence (soil) quantitative model (IRFMN) | ADI"

LOGVP_COL = "Vapour Pressure (CONCERT/Kode) | Predicted Vapour Pressure [log10(atm)]"
LOGVP_ASSESSMENT_COL = "Vapour Pressure (CONCERT/Kode) | Assessment"
LOGVP_ADI_COL = "Vapour Pressure (CONCERT/Kode) | ADI"

PWS_COL = "Water solubility model (IRFMN) | Predicted water solubility [-log(mol/L)]"
PWS_ASSESSMENT_COL = "Water solubility model (IRFMN) | Assessment"
PWS_ADI_COL = "Water solubility model (IRFMN) | ADI"

LRTP_REQUIRED_PREDICTION_COLUMNS = [
    LOGKOW_COL,
    HLAIR_COL,
    HLWATER_DAYS_COL,
    HLSOIL_DAYS_COL,
    LOGVP_COL,
    PWS_COL,
]

LRTP_REQUIRED_SOURCE_COLUMNS = set(LRTP_REQUIRED_PREDICTION_COLUMNS)

LRTP_NUMERIC_SOURCE_COLUMNS = LRTP_REQUIRED_PREDICTION_COLUMNS

DEFAULT_PARAMETERS = Path(__file__).with_name("lrtp_parameters.json")
PARAMETERS = json.loads(DEFAULT_PARAMETERS.read_text(encoding="utf-8"))
PARAMETER_SHA256 = _file_hash(DEFAULT_PARAMETERS)
if PARAMETERS.get("schema_version") != 1:
    raise ValueError("Unsupported LRTP parameter schema.")
POV_LIMIT_DAYS = PARAMETERS["reference_lines"]["POV_days"]
CTD_LIMIT_KM = PARAMETERS["reference_lines"]["CTD_km"]
TE_LIMIT_PERCENT = PARAMETERS["reference_lines"]["TE_percent"]
LOGKAW_WARNING_MIN, LOGKAW_WARNING_MAX = PARAMETERS["warning_ranges"]["logKaw"]
LOGKOW_WARNING_MIN, LOGKOW_WARNING_MAX = PARAMETERS["warning_ranges"]["logKow"]
HALF_LIFE_WARNING_MIN_H, HALF_LIFE_WARNING_MAX_H = PARAMETERS["warning_ranges"]["half_life_h"]
LOG_PARTITION_FATAL_MIN, LOG_PARTITION_FATAL_MAX = PARAMETERS["fatal_log_partition_range"]
OECD_TEMPERATURE_K = PARAMETERS["temperature_K"]
OECD_GAS_CONSTANT = PARAMETERS["gas_constant_Pa_m3_mol_K"]
LOG10_ATM_OVER_RT_L = math.log10(101_325 / (1000 * OECD_GAS_CONSTANT * OECD_TEMPERATURE_K))

LRTP_OUTPUT_COLUMNS = [
    "LRTP_logKaw_est",
    "LRTP_logKow",
    "LRTP_HLair_h",
    "LRTP_HLwater_h",
    "LRTP_HLsoil_h",
    "LRTP_POV_days",
    "LRTP_CTD_km",
    "LRTP_TE_percent",
    "LRTP_PhiAir",
    "LRTP_POV_exceeds_oecd_default",
    "LRTP_CTD_exceeds_oecd_default",
    "LRTP_TE_exceeds_oecd_default",
    "LRTP_input_status",
    "LRTP_warning_flags",
    "LRTP_evidence",
]


def _is_nullish(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() in {"", "-", "nan", "NaN"}:
        return True
    return False


def _as_float(value: Any) -> Optional[float]:
    if _is_nullish(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _json_default(value: Any) -> Any:
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def derive_log_kaw_from_vp_and_solubility(log_vp_atm: float, pws_mol_l: float) -> float:
    """
    Estimate log10(Kaw) from vapour pressure and water solubility.

    Args:
        log_vp_atm: log10 vapour pressure in atm.
        pws_mol_l: -log10 water solubility in mol/L.

    Returns:
        Estimated log10 dimensionless air-water partition coefficient.
    """
    return log_vp_atm + pws_mol_l + LOG10_ATM_OVER_RT_L


def _solve_linear_3x3(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a 3x3 linear system with Gaussian elimination and pivoting."""
    augmented = [list(map(float, row)) + [float(rhs)] for row, rhs in zip(matrix, vector)]
    n = 3
    for col in range(n):
        pivot = max(range(col, n), key=lambda row_idx: abs(augmented[row_idx][col]))
        if abs(augmented[pivot][col]) < 1e-300:
            raise ValueError("Singular mass-balance matrix")
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]

        pivot_value = augmented[col][col]
        for idx in range(col, n + 1):
            augmented[col][idx] /= pivot_value

        for row_idx in range(n):
            if row_idx == col:
                continue
            factor = augmented[row_idx][col]
            if factor == 0:
                continue
            for idx in range(col, n + 1):
                augmented[row_idx][idx] -= factor * augmented[col][idx]

    return [augmented[row_idx][n] for row_idx in range(n)]


def calculate_oecd_lrtp(
    *,
    log_kaw: float,
    log_kow: float,
    hl_air_h: float,
    hl_water_h: float,
    hl_soil_h: float,
) -> dict[str, Any]:
    """
    Calculate OECD Pov/LRTP screening metrics.

    Args:
        log_kaw: log10 dimensionless air-water partition coefficient.
        log_kow: log10 dimensionless octanol-water partition coefficient.
        hl_air_h: Air degradation half-life in hours.
        hl_water_h: Water degradation half-life in hours.
        hl_soil_h: Soil degradation half-life in hours.

    Returns:
        Dictionary with overall and emission-scenario-specific POV, CTD, and TE.
    """
    if not all(math.isfinite(v) for v in (log_kaw, log_kow, hl_air_h, hl_water_h, hl_soil_h)):
        raise ValueError("LRTP model inputs must be finite.")
    if min(hl_air_h, hl_water_h, hl_soil_h) <= 0:
        raise ValueError("OECD LRTP half-lives must be greater than zero.")

    z_sub = {(i, j): 0.0 for i in range(1, 4) for j in range(1, 4)}
    z_bulk = {i: 0.0 for i in range(1, 4)}
    d_value = {(i, j): 0.0 for i in range(1, 4) for j in range(1, 6)}
    d_inter = {(i, j, k): 0.0 for i in range(1, 4) for j in range(1, 5) for k in range(1, 5)}
    phi = {(i, j): 0.0 for i in range(1, 4) for j in range(1, 4)}
    phi_oc = {(i, j): 0.0 for i in range(1, 4) for j in range(1, 4)}
    rho_sub = {(i, j): 0.0 for i in range(1, 4) for j in range(1, 4)}
    rho_bulk = {i: 0.0 for i in range(1, 4)}

    area = {1: 510_000_000_000_000.0}
    area[2] = 0.71 * area[1]
    area[3] = area[1] - area[2]
    height = {1: 6000.0, 2: 100.0, 3: 0.1}
    volume = {i: area[i] * height[i] for i in range(1, 4)}

    phi[(3, 1)] = 0.00000000002
    phi[(1, 1)] = 1 - phi[(3, 1)]
    phi[(3, 2)] = 0.0000005
    phi[(2, 2)] = 1 - phi[(3, 2)]
    phi[(1, 3)] = 0.2
    phi[(2, 3)] = 0.3
    phi[(3, 3)] = 1 - phi[(1, 3)] - phi[(2, 3)]

    rho_sub[(1, 1)] = (0.029 * 101_325) / (OECD_GAS_CONSTANT * OECD_TEMPERATURE_K)
    rho_sub[(3, 1)] = 2400.0
    rho_sub[(3, 2)] = 2400.0
    rho_sub[(2, 2)] = 1000.0
    rho_sub[(1, 3)] = rho_sub[(1, 1)]
    rho_sub[(2, 3)] = rho_sub[(2, 2)]
    rho_sub[(3, 3)] = 2400.0

    phi_oc[(3, 2)] = 0.1
    phi_oc[(3, 3)] = 0.02

    mtc_awa = 30.0
    mtc_aww = 0.03
    mtc_rain = 9.7e-5
    mtc_qd = 10.8
    mtc_as = 0.04
    mtc_sw = 1e-5
    mtc_sconv = 4.54e-7
    mtc_sabl = 1.0
    mtc_wat_runoff = 3.9e-5
    mtc_soil_runoff = 2.3e-8
    mtc_1_strat = 0.064
    mtc_2_sink = 0.0052 / (1000 * phi_oc[(3, 2)] * rho_sub[(3, 2)])
    mtc_2_leach = 1.14e-4
    mtc_3_sink = 0.05 * mtc_sconv
    mtc_3_leach = 3e-6
    scav_ratio = 200_000.0
    windspeed = 14.4
    waterspeed = 0.072

    k_deg = {
        1: math.log(2) / hl_air_h,
        2: math.log(2) / hl_water_h,
        3: math.log(2) / hl_soil_h,
    }

    kaw = 10**log_kaw
    kow = 10**log_kow
    koa = 10 ** (log_kow - log_kaw)
    k_oc_l_kg = kow * 0.35
    k_qw_l_kg = k_oc_l_kg * phi_oc[(3, 2)]
    k_qw = k_qw_l_kg * rho_sub[(3, 2)] / 1000
    k_sw_l_kg = k_oc_l_kg * phi_oc[(3, 3)]
    k_sw = k_sw_l_kg * rho_sub[(3, 3)] / 1000
    k_qa = 0.42 * koa

    z_sub[(1, 1)] = 1 / (OECD_GAS_CONSTANT * OECD_TEMPERATURE_K)
    z_sub[(1, 3)] = z_sub[(1, 1)]
    z_sub[(2, 2)] = z_sub[(1, 1)] / kaw
    z_sub[(2, 3)] = z_sub[(2, 2)]
    z_sub[(3, 1)] = k_qa * z_sub[(1, 1)]
    z_sub[(3, 3)] = k_sw * z_sub[(2, 2)]
    z_sub[(3, 2)] = k_qw * z_sub[(2, 2)]

    z_bulk[1] = phi[(1, 1)] * z_sub[(1, 1)] + phi[(3, 1)] * z_sub[(3, 1)]
    rho_bulk[1] = phi[(1, 1)] * rho_sub[(1, 1)] + phi[(3, 1)] * rho_sub[(3, 1)]
    z_bulk[2] = phi[(2, 2)] * z_sub[(2, 2)] + phi[(3, 2)] * z_sub[(3, 2)]
    rho_bulk[2] = phi[(2, 2)] * rho_sub[(2, 2)] + phi[(3, 2)] * rho_sub[(3, 2)]
    z_bulk[3] = (
        phi[(1, 3)] * z_sub[(1, 3)]
        + phi[(2, 3)] * z_sub[(2, 3)]
        + phi[(3, 3)] * z_sub[(3, 3)]
    )
    rho_bulk[3] = (
        phi[(1, 3)] * rho_sub[(1, 3)]
        + phi[(2, 3)] * rho_sub[(2, 3)]
        + phi[(3, 3)] * rho_sub[(3, 3)]
    )

    d_inter[(1, 2, 1)] = area[2] / (
        1 / (mtc_awa * z_sub[(1, 1)]) + 1 / (mtc_aww * z_sub[(2, 2)])
    )
    d_inter[(1, 2, 2)] = area[2] * phi[(3, 1)] * mtc_qd * z_sub[(3, 1)]
    d_inter[(1, 2, 3)] = area[2] * mtc_rain * z_sub[(2, 2)]
    d_inter[(1, 2, 4)] = area[2] * scav_ratio * mtc_rain * z_sub[(3, 1)] * phi[(3, 1)]

    d_inter[(1, 3, 1)] = area[3] * z_sub[(1, 1)] / (
        z_sub[(1, 1)]
        / (mtc_as * z_sub[(1, 1)] + mtc_sw * z_sub[(2, 2)] + mtc_sconv * z_sub[(3, 3)])
        + 1 / mtc_sabl
    )
    d_inter[(1, 3, 2)] = area[3] * phi[(3, 1)] * mtc_qd * z_sub[(3, 1)]
    d_inter[(1, 3, 3)] = area[3] * mtc_rain * z_sub[(2, 2)]
    d_inter[(1, 3, 4)] = area[3] * scav_ratio * mtc_rain * z_sub[(3, 1)] * phi[(3, 1)]

    d_inter[(2, 1, 1)] = d_inter[(1, 2, 1)]
    d_inter[(3, 1, 1)] = d_inter[(1, 3, 1)]
    d_inter[(3, 2, 1)] = area[3] * mtc_wat_runoff * z_sub[(2, 3)]
    d_inter[(3, 2, 2)] = area[3] * mtc_soil_runoff * z_sub[(3, 3)]

    d_inter[(1, 4, 1)] = mtc_1_strat * area[1] * z_sub[(1, 1)]
    d_inter[(2, 4, 1)] = mtc_2_sink * area[2] * z_sub[(3, 2)]
    d_inter[(2, 4, 2)] = mtc_2_leach * area[2] * z_sub[(2, 2)]
    d_inter[(3, 4, 1)] = mtc_3_sink * area[3] * z_sub[(3, 3)]
    d_inter[(3, 4, 2)] = mtc_3_leach * area[3] * z_sub[(2, 3)]

    d_te = windspeed * 1000 * (area[1] ** 0.5) * height[1] * z_bulk[1]

    d_value[(1, 5)] = volume[1] * z_sub[(1, 1)] * k_deg[1]
    for comp in range(2, 4):
        d_value[(comp, 5)] = volume[comp] * z_bulk[comp] * k_deg[comp]

    for source in range(1, 4):
        for dest in range(1, 5):
            for process in range(1, 5):
                d_value[(source, dest)] += d_inter[(source, dest, process)]

    fugacity: dict[tuple[int, int], float] = {}
    inventory: dict[tuple[int, int], float] = {}
    inventory_total: dict[int, float] = {}

    for scenario in range(1, 4):
        emissions = {1: 0.0, 2: 0.0, 3: 0.0}
        emissions[scenario] = 100.0

        matrix: list[list[float]] = []
        vector: list[float] = []
        for comp in range(1, 4):
            row: list[float] = []
            for unknown in range(1, 4):
                if unknown == comp:
                    row.append(sum(d_value[(comp, dest)] for dest in range(1, 6)))
                else:
                    row.append(-d_value[(unknown, comp)])
            matrix.append(row)
            vector.append(emissions[comp])

        solution = _solve_linear_3x3(matrix, vector)
        inventory_total[scenario] = 0.0
        for comp, value in enumerate(solution, start=1):
            fugacity[(comp, scenario)] = value
            inventory[(comp, scenario)] = value * z_bulk[comp] * volume[comp]
            inventory_total[scenario] += inventory[(comp, scenario)]

    pov_em: dict[int, float] = {}
    ctd_air_em = {1: 0.0, 2: 0.0, 3: 0.0}
    ctd_water_em = {1: 0.0, 2: 0.0, 3: 0.0}
    te_em: dict[int, float] = {}

    ctd_air_em[1] = inventory[(1, 1)] * windspeed / 100
    ctd_water_em[2] = inventory[(2, 2)] * waterspeed / 100
    ctd = max(ctd_air_em[1], ctd_water_em[2])

    pov = 0.0
    te = 0.0
    for scenario in range(1, 4):
        degradation_flux = (
            fugacity[(1, scenario)] * d_value[(1, 5)]
            + fugacity[(2, scenario)] * d_value[(2, 5)]
            + fugacity[(3, scenario)] * d_value[(3, 5)]
        )
        pov_em[scenario] = inventory_total[scenario] / 24 / degradation_flux
        pov = max(pov, pov_em[scenario])

        te_em[scenario] = (
            fugacity[(1, scenario)] ** 2 * (d_value[(1, 2)] + d_value[(1, 3)]) * d_te
        ) / 100**2 * 100
        te = max(te, te_em[scenario])

    phi_air = phi[(3, 1)] * z_sub[(3, 1)] / z_bulk[1]

    return {
        "POV_days": pov,
        "CTD_km": ctd,
        "TE_percent": te,
        "PhiAir": phi_air,
        "emission_scenarios": {
            "air": {
                "POV_days": pov_em[1],
                "CTDair_km": ctd_air_em[1],
                "CTDwater_km": None,
                "TE_percent": te_em[1],
            },
            "water": {
                "POV_days": pov_em[2],
                "CTDair_km": None,
                "CTDwater_km": ctd_water_em[2],
                "TE_percent": te_em[2],
            },
            "soil": {
                "POV_days": pov_em[3],
                "CTDair_km": None,
                "CTDwater_km": None,
                "TE_percent": te_em[3],
            },
        },
    }


def _collect_source_quality(row: pd.Series) -> dict[str, Any]:
    source_map = {
        "logKow": (LOGKOW_ASSESSMENT_COL, LOGKOW_ADI_COL),
        "HLair": (HLAIR_ASSESSMENT_COL, HLAIR_ADI_COL),
        "HLwater": (HLWATER_ASSESSMENT_COL, HLWATER_ADI_COL),
        "HLsoil": (HLSOIL_ASSESSMENT_COL, HLSOIL_ADI_COL),
        "logVP": (LOGVP_ASSESSMENT_COL, LOGVP_ADI_COL),
        "water_solubility": (PWS_ASSESSMENT_COL, PWS_ADI_COL),
    }
    quality: dict[str, Any] = {}
    for name, (assessment_col, adi_col) in source_map.items():
        details: dict[str, Any] = {}
        if assessment_col in row.index and not _is_nullish(row.get(assessment_col)):
            details["assessment"] = str(row.get(assessment_col))
        if adi_col in row.index:
            details["ADI"] = _as_float(row.get(adi_col))
        if details:
            quality[name] = details
    return quality


def _validate_inputs(inputs: dict[str, Optional[float]]) -> tuple[str, list[str]]:
    missing = [name for name, value in inputs.items() if value is None]
    if missing:
        return "missing", [f"missing_{name}" for name in missing]

    flags: list[str] = []
    status = "ok"
    log_kaw = inputs["log_kaw"]
    log_kow = inputs["log_kow"]
    hl_air_h = inputs["hl_air_h"]
    hl_water_h = inputs["hl_water_h"]
    hl_soil_h = inputs["hl_soil_h"]
    assert log_kaw is not None
    assert log_kow is not None
    assert hl_air_h is not None
    assert hl_water_h is not None
    assert hl_soil_h is not None

    if not LOG_PARTITION_FATAL_MIN <= log_kaw <= LOG_PARTITION_FATAL_MAX:
        flags.append("invalid_logKaw_outside_fatal_range")
    if not LOG_PARTITION_FATAL_MIN <= log_kow <= LOG_PARTITION_FATAL_MAX:
        flags.append("invalid_logKow_outside_fatal_range")
    for name, value in [("HLair", hl_air_h), ("HLwater", hl_water_h), ("HLsoil", hl_soil_h)]:
        if value <= 0:
            flags.append(f"invalid_{name}_nonpositive")
    if flags:
        return "invalid", flags

    if not LOGKAW_WARNING_MIN <= log_kaw <= LOGKAW_WARNING_MAX:
        flags.append("warning_logKaw_outside_oecd_default_range")
    if not LOGKOW_WARNING_MIN <= log_kow <= LOGKOW_WARNING_MAX:
        flags.append("warning_logKow_outside_oecd_default_range")
    for name, value in [("HLair", hl_air_h), ("HLwater", hl_water_h), ("HLsoil", hl_soil_h)]:
        if not HALF_LIFE_WARNING_MIN_H <= value <= HALF_LIFE_WARNING_MAX_H:
            flags.append(f"warning_{name}_outside_oecd_default_range")

    if flags:
        status = "warning"
    return status, flags


def _empty_lrtp_record(status: str, flags: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    record = {column: None for column in LRTP_OUTPUT_COLUMNS}
    record["LRTP_input_status"] = status
    record["LRTP_warning_flags"] = "|".join(flags)
    record["LRTP_evidence"] = _json_dumps(evidence)
    return record


def _calculate_row_lrtp(row: pd.Series) -> dict[str, Any]:
    log_kow = _as_float(row.get(LOGKOW_COL))
    hl_air_h = _as_float(row.get(HLAIR_COL))
    hl_water_days = _as_float(row.get(HLWATER_DAYS_COL))
    hl_soil_days = _as_float(row.get(HLSOIL_DAYS_COL))
    log_vp_atm = _as_float(row.get(LOGVP_COL))
    pws_mol_l = _as_float(row.get(PWS_COL))

    log_kaw = None
    if log_vp_atm is not None and pws_mol_l is not None:
        log_kaw = derive_log_kaw_from_vp_and_solubility(log_vp_atm, pws_mol_l)

    inputs = {
        "log_kaw": log_kaw,
        "log_kow": log_kow,
        "hl_air_h": hl_air_h,
        "hl_water_h": None if hl_water_days is None else hl_water_days * 24,
        "hl_soil_h": None if hl_soil_days is None else hl_soil_days * 24,
    }
    evidence = {
        "method": "OECD Pov/LRTP Screening Tool three-compartment fugacity model",
        "input_source": "VEGA/QSAR predicted properties",
        "logKaw_derivation": {
            "formula": "log10(Kaw)=log10(VP_atm)+(-log10(S_mol_L))+log10(101325/(1000*R*T))",
            "constant": LOG10_ATM_OVER_RT_L,
            "logVP_atm": log_vp_atm,
            "pWS_mol_L": pws_mol_l,
        },
        "source_quality": _collect_source_quality(row),
    }

    status, flags = _validate_inputs(inputs)
    if status in {"missing", "invalid"}:
        evidence["inputs"] = inputs
        evidence["status"] = status
        evidence["flags"] = flags
        return _empty_lrtp_record(status, flags, evidence)

    try:
        result = calculate_oecd_lrtp(
            log_kaw=inputs["log_kaw"],
            log_kow=inputs["log_kow"],
            hl_air_h=inputs["hl_air_h"],
            hl_water_h=inputs["hl_water_h"],
            hl_soil_h=inputs["hl_soil_h"],
        )
        if not all(math.isfinite(result[key]) for key in ("POV_days", "CTD_km", "TE_percent", "PhiAir")):
            raise ValueError("Non-finite model output")
    except (ArithmeticError, OverflowError, ValueError) as exc:
        evidence["inputs"] = inputs
        evidence["status"] = "calculation_error"
        evidence["calculation_error"] = str(exc)
        return _empty_lrtp_record("calculation_error", [type(exc).__name__], evidence)

    pov = result["POV_days"]
    ctd = result["CTD_km"]
    te = result["TE_percent"]
    evidence["inputs"] = inputs
    evidence["status"] = status
    evidence["flags"] = flags
    evidence["result"] = result
    evidence["criteria"] = {
        "POV_limit_days": POV_LIMIT_DAYS,
        "CTD_limit_km": CTD_LIMIT_KM,
        "TE_limit_percent": TE_LIMIT_PERCENT,
    }

    return {
        "LRTP_logKaw_est": inputs["log_kaw"],
        "LRTP_logKow": inputs["log_kow"],
        "LRTP_HLair_h": inputs["hl_air_h"],
        "LRTP_HLwater_h": inputs["hl_water_h"],
        "LRTP_HLsoil_h": inputs["hl_soil_h"],
        "LRTP_POV_days": pov,
        "LRTP_CTD_km": ctd,
        "LRTP_TE_percent": te,
        "LRTP_PhiAir": result["PhiAir"],
        "LRTP_POV_exceeds_oecd_default": bool(pov > POV_LIMIT_DAYS),
        "LRTP_CTD_exceeds_oecd_default": bool(ctd > CTD_LIMIT_KM),
        "LRTP_TE_exceeds_oecd_default": bool(te > TE_LIMIT_PERCENT),
        "LRTP_input_status": status,
        "LRTP_warning_flags": "|".join(flags),
        "LRTP_evidence": _json_dumps(evidence),
    }


# These fields are withheld from analysis when identity or numerical checks fail.
VALUE_COLUMNS = LRTP_OUTPUT_COLUMNS[:12]
METRIC_COLUMNS = LRTP_OUTPUT_COLUMNS[5:12]


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def _verify_outputs(folder: Path, manifest: dict) -> None:
    for filename, digest in manifest["output_sha256"].items():
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise ValueError("Upstream artifact filenames must be basenames.")
        if _file_hash(folder / filename) != digest:
            raise ValueError(f"Upstream artifact fingerprint differs: {filename}")


def _project_available(compounds: pd.DataFrame, historical: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep historical values separate from the table intended for later analysis."""
    output = compounds.merge(historical[["inchikey", *LRTP_OUTPUT_COLUMNS]], on="inchikey",
                             how="left", validate="one_to_one")
    output["calculation_status"] = output["LRTP_input_status"]
    verified = output["qsar_identity_verified"].map(str).eq("True")
    calculable = output["calculation_status"].isin(["ok", "warning"])
    output["lrtp_available"] = verified & calculable
    output["lrtp_exclusion_reason"] = ""
    output.loc[~calculable, "lrtp_exclusion_reason"] = output.loc[~calculable, "calculation_status"].map(
        lambda s: "calculation_" + s)
    output.loc[~verified, "lrtp_exclusion_reason"] = "no_verified_report_association"
    review = output["qsar_identity_status"].eq("review_required")
    output.loc[review, "lrtp_exclusion_reason"] = "identity_review_required"
    changes = []
    for _, row in output.loc[review].iterrows():
        for column in VALUE_COLUMNS:
            changes.append({"inchikey": row["inchikey"], "qsar_inchikey": row["qsar_inchikey"],
                            "vega_row_no": row["vega_row_no"], "field": column,
                            "historical_value": row[column], "analysis_value": None,
                            "exclusion_reason": "identity_review_required",
                            "identity_reason": row["qsar_identity_reason"]})
    # Nullable values preserve the distinction between an unavailable result and zero/False.
    for column in VALUE_COLUMNS:
        output[column] = output[column].astype(object)
        output.loc[~output["lrtp_available"], column] = None
    output.loc[review, "LRTP_input_status"] = "identity_review_required"
    # Historical evidence contains scenario results: never hide unverified values inside this JSON.
    output = output.drop(columns="LRTP_evidence")
    return output, pd.DataFrame(changes, columns=["inchikey", "qsar_inchikey", "vega_row_no", "field",
        "historical_value", "analysis_value", "exclusion_reason", "identity_reason"])


@dataclass
class LRTPResult:
    historical: pd.DataFrame
    compounds: pd.DataFrame
    input_audit: pd.DataFrame
    isolation_audit: pd.DataFrame
    anomaly_sources: pd.DataFrame
    anomaly_reports: pd.DataFrame
    manifest: dict

    def write_reports(self, output_dir: str | Path) -> None:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in (("lrtp_historical_results", self.historical),
                            ("compound_lrtp", self.compounds), ("lrtp_input_audit", self.input_audit),
                            ("identity_isolation_audit", self.isolation_audit),
                            ("identity_anomaly_sources", self.anomaly_sources),
                            ("identity_anomaly_reports", self.anomaly_reports)):
            path = folder / (name + ".csv")
            frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            outputs[path.name] = _file_hash(path)
        (folder / "lrtp_manifest.json").write_text(json.dumps({**self.manifest, "output_sha256": outputs},
            indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def integrate_lrtp(qsar_results: str | Path) -> LRTPResult:
    """Read verified Stage 3A artifacts without modifying them or running later scoring."""
    folder = Path(qsar_results)
    manifest_path = folder / "qsar_manifest.json"
    manifest_hash = _file_hash(manifest_path)
    upstream = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_artifacts = {"compound_qsar.csv", "identity_anomaly_sources.csv", "identity_anomaly_reports.csv"}
    if not required_artifacts <= set(upstream["output_sha256"]):
        raise ValueError("Required Stage 3A artifacts are missing from the fingerprint manifest.")
    _verify_outputs(folder, upstream)
    if _file_hash(DEFAULT_PARAMETERS) != PARAMETER_SHA256:
        raise ValueError("LRTP parameters changed after module import; restart the process.")
    compounds = _read_csv(folder / "compound_qsar.csv")
    required = {"inchikey", "qsar_inchikey", "vega_row_no", "qsar_identity_status",
                "qsar_identity_verified", "qsar_identity_reason", *LRTP_REQUIRED_PREDICTION_COLUMNS}
    declared = PARAMETERS["input_mapping"]
    if [m["column"] for m in declared] != LRTP_REQUIRED_PREDICTION_COLUMNS:
        raise ValueError("Declared LRTP input mapping differs from the calculation kernel.")
    for mapping in declared:
        required.update([mapping["assessment_column"], mapping["adi_column"]])
    report_hashes = {item["filename"]: item["sha256"] for item in upstream["inputs"]}
    if any(report_hashes.get(m["report_filename"]) != m["report_sha256"] for m in declared):
        raise ValueError("LRTP property mappings do not match the frozen report versions.")
    if not required <= set(compounds):
        raise ValueError(f"Missing LRTP source columns: {sorted(required - set(compounds))}")
    if compounds.empty or compounds["inchikey"].eq("").any() or compounds["inchikey"].duplicated().any():
        raise ValueError("LRTP integration requires unique, non-empty full identities.")
    if any(c.startswith("LRTP_") or c == "calculation_status" for c in compounds):
        raise ValueError("Stage 3A input already contains LRTP results.")
    allowed = {"exact_key_match", "review_required", "no_report_association"}
    if not set(compounds["qsar_identity_status"]) <= allowed:
        raise ValueError("Unknown upstream identity status.")
    expected_verified = compounds["qsar_identity_status"].eq("exact_key_match").map(str)
    if not expected_verified.equals(compounds["qsar_identity_verified"]):
        raise ValueError("Identity status and verification flag disagree.")
    review = compounds.loc[compounds["qsar_identity_status"].eq("review_required")]
    expected_rows = upstream["frozen_batch"]["identity_review_rows"]
    if sorted(review["vega_row_no"].astype(int).unique()) != sorted(expected_rows):
        raise ValueError("Identity-review rows differ from the frozen Stage 3A declaration.")
    records, inputs = [], []
    for _, row in compounds.iterrows():
        record = {**{c: row[c] for c in ("inchikey", "qsar_inchikey", "vega_row_no", "qsar_identity_status",
                                       "qsar_identity_verified", "qsar_identity_reason")},
                  "result_role": "historical_reproduction_only", **_calculate_row_lrtp(row)}
        records.append(record)
        evidence = json.loads(record["LRTP_evidence"])
        inputs.append({"inchikey": row["inchikey"], "qsar_inchikey": row["qsar_inchikey"],
                       "vega_row_no": row["vega_row_no"],
                       **{c: row[c] for c in LRTP_REQUIRED_PREDICTION_COLUMNS},
                       **evidence["inputs"], "calculation_status": record["LRTP_input_status"],
                       "warning_flags": record["LRTP_warning_flags"],
                       "qsar_identity_status": row["qsar_identity_status"],
                       "qsar_identity_reason": row["qsar_identity_reason"],
                       "source_quality_json": _json_dumps(evidence["source_quality"])})
    historical = pd.DataFrame(records)
    available, isolation = _project_available(compounds, historical)
    input_audit = pd.DataFrame(inputs).merge(
        available[["inchikey", "lrtp_available", "lrtp_exclusion_reason"]],
        on="inchikey", how="left", validate="one_to_one")
    sources = _read_csv(folder / "identity_anomaly_sources.csv")
    reports = _read_csv(folder / "identity_anomaly_reports.csv")
    if set(sources["inchikey"]) != set(review["inchikey"]):
        raise ValueError("Incomplete identity-review source provenance.")
    # Preserve all original fields; connect exclusion reasons without changing source evidence.
    sources["lrtp_exclusion_reason"] = "identity_review_required"
    sources["identity_reason"] = sources["inchikey"].map(review.set_index("inchikey")["qsar_identity_reason"])
    reports["lrtp_exclusion_reason"] = "identity_review_required"
    reports["identity_reason"] = reports["qsar_inchikey"].map(
        review.drop_duplicates("qsar_inchikey").set_index("qsar_inchikey")["qsar_identity_reason"])
    if reports["identity_reason"].isna().any() or set(reports["qsar_inchikey"]) != set(review["qsar_inchikey"]):
        raise ValueError("Incomplete or unrelated identity-review report provenance.")
    _verify_outputs(folder, upstream)
    if _file_hash(manifest_path) != manifest_hash or _file_hash(DEFAULT_PARAMETERS) != PARAMETER_SHA256:
        raise ValueError("Inputs or parameters changed during LRTP integration.")
    counts = {"compounds": len(compounds), "historically_calculable": int(historical["LRTP_input_status"].isin(["ok", "warning"]).sum()),
              "available_after_identity_check": int(available["lrtp_available"].sum()),
              "identity_excluded_compounds": len(review), "identity_source_records": len(sources),
              "identity_report_links": len(reports)}
    manifest = {"schema_version": 1, "policy_version": PARAMETERS["policy_version"],
                "scope": PARAMETERS["scope"], "upstream_qsar_manifest_sha256": manifest_hash,
                "parameters_sha256": PARAMETER_SHA256, "implementation_sha256": _file_hash(Path(__file__)),
                "upstream_output_sha256": upstream["output_sha256"],
                "runtime": {"python": platform.python_version(), "pandas": pd.__version__},
                "counts": counts, "historical_status_counts": historical["LRTP_input_status"].value_counts().to_dict(),
                "reference_lines": PARAMETERS["reference_lines"],
                "historical_source": PARAMETERS["historical_source"],
                "interpretation": "Historical values reproduce archived associations. Analysis outputs withhold unverified identities. Availability does not establish QSAR reliability or independent OECD-tool validation."}
    return LRTPResult(historical, available, input_audit, isolation, sources, reports, manifest)
