"""Incident Report (IR) generator for high-risk inbound mesh messages.

Called from the worker thread AFTER the reply has been sent — so triage
never delays the user's answer. If risk is HIGH or CRITICAL, writes a
structured JSON report to incidents/<timestamp>_<node_id>.json.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("copilot.incident")

RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
TRIGGER_LEVELS = {"MEDIUM", "HIGH", "CRITICAL"}

INCIDENTS_DIR = Path(__file__).parent.parent / "incidents"

_TRIAGE_PROMPT = """\
You are an emergency triage assistant for a search-and-rescue base station.
A distress message arrived over a LoRa radio mesh from a remote sender.
Assess the risk level and produce a brief incident summary.

Respond ONLY with a valid JSON object — no markdown, no extra text:
{
  "risk": "LOW|MEDIUM|HIGH|CRITICAL",
  "summary": "<one sentence describing the situation>",
  "rationale": "<1-2 sentences explaining the risk level>",
  "recommended_actions": ["<action 1>", "<action 2>"]
}

Risk level guide — assign the HIGHEST level that fits any single factor:
  CRITICAL — any of: unconscious / unresponsive, severe uncontrolled bleeding,
             completely trapped with no self-rescue, extreme weather exposure
             with no shelter, multiple serious injuries
  HIGH     — any of: broken bone / significant injury, lost after dark or in
             bad weather, no shelter when temperature is dropping, alone and
             unable to move, rapidly worsening symptoms
  MEDIUM   — minor injury still able to move, lost but has shelter/gear,
             stable situation but seeking urgent guidance
  LOW      — general information, no current distress, theoretical question

All text fields in the JSON (summary, rationale, recommended_actions) MUST be in English regardless of the sender's language.

/no_think"""


def assess_risk(
    question: str,
    answer: str,
    base_url: str,
    model: str,
) -> dict[str, Any]:
    """Call the LLM to triage the incoming message.

    Returns a dict with keys: risk, summary, rationale, recommended_actions.
    Falls back to MEDIUM on any error so we never silently drop a real emergency.
    """
    user_msg = f"Sender message: {question}\n\nBot response sent: {answer}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _TRIAGE_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": 400,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(f"{base_url}/chat/completions", json=payload)
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()
        # Strip <think>...</think> wrapper Qwen3 sometimes emits
        if "</think>" in raw:
            raw = raw[raw.rfind("</think>") + len("</think>"):].strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start >= 0 and end > start:
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw[start:end])
            data = json.loads(cleaned)
            if data.get("risk") in RISK_LEVELS:
                return data
        log.warning("triage: unexpected LLM output — %r", raw[:120])
    except Exception as e:  # noqa: BLE001
        log.warning("triage LLM call failed: %s", e)

    return {
        "risk": "MEDIUM",
        "summary": "Risk assessment unavailable — treated as MEDIUM.",
        "rationale": "Triage call failed; defaulting to MEDIUM for safety.",
        "recommended_actions": ["Monitor sender", "Check last known GPS"],
    }


def build_node_info(interface, packet: dict) -> dict[str, Any]:
    """Extract sender identity, GPS, battery, and RF link from the node DB + packet."""
    from basestation import (  # local import to avoid circular deps
        _lookup_node, _base_position, _my_node_num,
        _haversine_km, _bearing_deg, _compass,
    )

    sender = packet.get("from")
    node = _lookup_node(interface, sender) or {}
    user = node.get("user") or {}
    pos = node.get("position") or {}
    dm = node.get("deviceMetrics") or {}

    info: dict[str, Any] = {
        "from_num": sender,
        "from_id": user.get("id") or packet.get("fromId"),
        "long_name": user.get("longName"),
        "short_name": user.get("shortName"),
        "hw_model": user.get("hwModel"),
        "lat": pos.get("latitude"),
        "lon": pos.get("longitude"),
        "alt_m": pos.get("altitude"),
        "pos_age_s": (int(time.time() - pos["time"]) if pos.get("time") else None),
        "battery_pct": dm.get("batteryLevel"),
        "voltage": dm.get("voltage"),
        "rx_snr": packet.get("rxSnr"),
        "rx_rssi": packet.get("rxRssi"),
        "hops_away": node.get("hopsAway"),
        "hop_limit": packet.get("hopLimit"),
    }

    # Distance + bearing from base
    try:
        blat, blon, _ = _base_position(interface)
        if blat is not None and info["lat"] is not None and sender != _my_node_num(interface):
            dist_km = _haversine_km(blat, blon, info["lat"], info["lon"])
            brg = _bearing_deg(blat, blon, info["lat"], info["lon"])
            info["dist_from_base_m"] = round(dist_km * 1000)
            info["bearing_deg"] = round(brg)
            info["bearing_compass"] = _compass(brg)
    except Exception:
        pass

    return info


def _risk_badge(risk: str) -> str:
    return {"CRITICAL": "🔴 CRITICAL", "HIGH": "🟠 HIGH",
            "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW"}.get(risk, risk)


def _fmt_pos_age(seconds) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 90:
        return f"{seconds}s ago"
    if seconds < 5400:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


def _render_md(report: dict[str, Any]) -> str:
    r = report
    inc = r["incident"]
    snd = r["sender"]
    loc = r["location"]
    dev = r["device"]
    rf  = r["rf_link"]

    name = snd.get("long_name") or snd.get("node_id") or "unknown"
    short = snd.get("short_name") or ""
    node_line = f"{name} ({short})  |  {snd.get('node_id') or '—'}"

    gps = "—"
    if loc.get("lat") is not None:
        gps = f"{loc['lat']:.5f}, {loc['lon']:.5f}"
        if loc.get("alt_m") is not None:
            gps += f"  |  Alt {loc['alt_m']} m"

    dist = "—"
    if loc.get("dist_from_base_m") is not None:
        dist = f"{loc['dist_from_base_m']} m  |  {loc.get('bearing_deg', '?')}° {loc.get('bearing_compass', '')}"

    batt = "—"
    if dev.get("battery_pct") is not None:
        batt = f"{dev['battery_pct']}%"
        if dev.get("voltage") is not None:
            batt += f"  ({dev['voltage']:.2f} V)"

    rf_line = "—"
    parts = []
    if rf.get("rx_rssi") is not None:
        parts.append(f"RSSI {rf['rx_rssi']} dBm")
    if rf.get("rx_snr") is not None:
        parts.append(f"SNR {rf['rx_snr']}")
    if rf.get("hops_away") is not None:
        parts.append(f"{rf['hops_away']} hop(s)")
    if parts:
        rf_line = "  |  ".join(parts)

    actions = "\n".join(
        f"  {i+1}. {a}" for i, a in enumerate(inc.get("recommended_actions") or [])
    )

    ts_utc = r.get("generated_at", "")
    lines = [
        f"# {_risk_badge(r['risk_level'])} INCIDENT REPORT",
        f"",
        f"Generated : {ts_utc}",
        f"Node      : {node_line}",
        f"Hardware  : {snd.get('hw_model') or '—'}",
        f"",
        f"## Situation",
        f"**Message** : {inc['message']}",
        f"**Summary** : {inc.get('summary', '—')}",
        f"",
        f"*{inc.get('rationale', '')}*",
        f"",
        f"**Recommended Actions**",
        actions or "  —",
        f"",
        f"## Location",
        f"GPS      : {gps}",
        f"Age      : {_fmt_pos_age(loc.get('pos_age_s'))}",
        f"From base: {dist}",
        f"",
        f"## Device",
        f"Battery : {batt}",
        f"",
        f"## RF Link",
        rf_line,
    ]
    return "\n".join(lines) + "\n"


def write_ir(
    question: str,
    answer: str,
    risk_data: dict[str, Any],
    node_info: dict[str, Any],
) -> Path | None:
    """Write .json + .md IR pair to incidents/. Returns the .md path, or None if below threshold."""
    risk = risk_data.get("risk", "UNKNOWN")
    if risk not in TRIGGER_LEVELS:
        return None

    INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc)
    node_id = (node_info.get("from_id") or str(node_info.get("from_num", "unknown"))).strip("!")
    stem = f"{ts.strftime('%Y%m%d_%H%M%S')}_{node_id}"

    report = {
        "schema": "survival-copilot-ir/v1",
        "generated_at": ts.isoformat(timespec="seconds"),
        "risk_level": risk,
        "incident": {
            "message": question,
            "bot_response": answer,
            "summary": risk_data.get("summary", ""),
            "rationale": risk_data.get("rationale", ""),
            "recommended_actions": risk_data.get("recommended_actions", []),
        },
        "sender": {
            "node_id": node_info.get("from_id"),
            "node_num": node_info.get("from_num"),
            "long_name": node_info.get("long_name"),
            "short_name": node_info.get("short_name"),
            "hw_model": node_info.get("hw_model"),
        },
        "location": {
            "lat": node_info.get("lat"),
            "lon": node_info.get("lon"),
            "alt_m": node_info.get("alt_m"),
            "pos_age_s": node_info.get("pos_age_s"),
            "dist_from_base_m": node_info.get("dist_from_base_m"),
            "bearing_deg": node_info.get("bearing_deg"),
            "bearing_compass": node_info.get("bearing_compass"),
        },
        "device": {
            "battery_pct": node_info.get("battery_pct"),
            "voltage": node_info.get("voltage"),
        },
        "rf_link": {
            "rx_snr": node_info.get("rx_snr"),
            "rx_rssi": node_info.get("rx_rssi"),
            "hops_away": node_info.get("hops_away"),
            "hop_limit": node_info.get("hop_limit"),
        },
    }

    try:
        (INCIDENTS_DIR / f"{stem}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md_path = INCIDENTS_DIR / f"{stem}.md"
        md_path.write_text(_render_md(report), encoding="utf-8")
        return md_path
    except Exception as e:
        log.error("failed to write IR: %s", e)
        return None
