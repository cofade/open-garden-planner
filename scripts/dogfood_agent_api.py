"""Dogfood harness: drive the live Agent API from OUTSIDE the app process.

Why this exists
---------------
``tests/integration/test_agent_api_*.py`` start a real ``AgentApiServer`` but
inside the test process, with providers the test supplies. That covers the
transport and the domain logic, and it cannot cover three things:

* the **frozen exe** (PyInstaller hidden imports, resources, the windowed-exe
  ``sys.stdout is None`` condition of #291),
* the **real** provider wiring in ``application.py``,
* a **real MCP client's** own quirks.

This script launches the built exe, connects with the same ``mcp``
streamable-HTTP client a real harness uses, and drives the tools end to end.

    venv/Scripts/python.exe scripts/dogfood_agent_api.py            # drive the tools
    venv/Scripts/python.exe scripts/dogfood_agent_api.py --repair   # restore defaults

It requires no credentials and no network: the token is generated locally and
the server is loopback-only.

MUTATION TESTING IT (read this before trusting a "PASS")
--------------------------------------------------------
This script exercises the **built exe**, so it is only sensitive to source you
have actually rebuilt. Mutating ``src/`` and re-running it proves nothing: the
four mutations tried that way all "survived" purely because the exe still held
the old code. Verified: with a PyInstaller rebuild, mutating the stored dates is
caught immediately by the ``stored dates match`` check.

To mutation-test it, rebuild between mutations:

    # mutate src/...
    venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
    venv/Scripts/python.exe scripts/dogfood_agent_api.py   # expect DOGFOOD: FAIL
    # restore src/... and rebuild before the next one

SAFETY
------
It temporarily enables Agent API writes and points the app at a scratch
``.ogp`` in a temp directory, then **restores every setting it touched** in an
outermost ``finally``. ``restore()`` is deliberately defensive: an earlier
version raised *inside* restore (the token is a read-only property, so it has no
setter), which left ``writes_enabled`` on and the port pointing at a scratch
value. A harness that damages the developer's configuration is worse than no
harness, so the baseline is captured before seeding and restore never raises.

The one residual risk: a hard kill (Ctrl-C at the wrong moment, machine
shutdown) skips the ``finally`` and leaves ``writes_enabled=True`` on a scratch
port. To undo by hand, run this with ``--repair``.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

DEFAULT_EXE = REPO / "dist" / "OpenGardenPlanner" / "OpenGardenPlanner.exe"


# --------------------------------------------------------------------------- #
# settings snapshot / restore
# --------------------------------------------------------------------------- #

def _app_settings():
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.app.settings import AppSettings

    app = QApplication.instance() or QApplication([])
    return AppSettings(), app


def snapshot_settings() -> dict:
    s, _app = _app_settings()
    return {
        "enabled": s.agent_api_enabled,
        "writes": s.agent_api_writes_enabled,
        "port": s.agent_api_port,
        "token": s._settings.value(s.KEY_AGENT_API_TOKEN, "", type=str),
        # Opening the scratch plan goes through add_recent_file, which persists
        # to QSettings. Un-snapshotted, every run pushes a real plan out of the
        # developer's 10-slot MRU list -- the SAFETY note claimed otherwise.
        "recent": s._settings.value(s.KEY_RECENT_FILES, "", type=str),
    }


def apply_settings(port: int) -> str:
    s, _app = _app_settings()
    s.agent_api_enabled = True
    s.agent_api_writes_enabled = True
    s.agent_api_port = port
    token = s.regenerate_agent_api_token()
    s.sync()
    return token


def restore_settings(before: dict) -> list[str]:
    """Put every touched setting back. NEVER raises; returns what it restored."""
    problems: list[str] = []
    try:
        s, _app = _app_settings()
        s.agent_api_enabled = before["enabled"]
        s.agent_api_writes_enabled = before["writes"]
        s.agent_api_port = before["port"]
        # `agent_api_token` is a READ-ONLY property (no setter). Write the key
        # directly, and REMOVE it when there was none, so the first-run
        # auto-generation is restored rather than pinned to a scratch token.
        if before["token"]:
            s._settings.setValue(s.KEY_AGENT_API_TOKEN, before["token"])
        else:
            s._settings.remove(s.KEY_AGENT_API_TOKEN)
        if before.get("recent"):
            s._settings.setValue(s.KEY_RECENT_FILES, before["recent"])
        else:
            s._settings.remove(s.KEY_RECENT_FILES)
        s.sync()
        problems.append(
            f"enabled={s.agent_api_enabled} writes={s.agent_api_writes_enabled} "
            f"port={s.agent_api_port} token="
            f"{'restored' if before['token'] else 'removed (regenerates)'}"
        )
    except Exception:  # noqa: BLE001 - reporting beats masking
        problems.append("restore FAILED: " + traceback.format_exc(limit=2))
    return problems


# --------------------------------------------------------------------------- #
# app + client
# --------------------------------------------------------------------------- #

def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def empty_plan(path: Path) -> None:
    """An EMPTY .ogp - the bed is created through the agent itself.

    A hand-written bed item does not match the real save schema; an earlier
    version of this harness did exactly that and the agent correctly refused to
    find the bed. Creating it with ``create_object`` removes the invented format.
    """
    doc = {
        "version": "1.4",
        "meta": {"name": "dogfood", "created": "2026-10-01", "modified": "2026-10-01"},
        "settings": {"units": "cm", "grid_size": 50, "snap_enabled": True},
        "canvas": {"width": 1000, "height": 800, "background_color": "#ffffff"},
        "layers": [],
        "objects": [],
        "location": {
            "latitude": 52.52,
            "longitude": 13.405,
            "elevation_m": 34,
            "frost_dates": {
                "last_spring_frost": "04-15",
                "first_fall_frost": "10-15",
                "hardiness_zone": "7a",
            },
        },
        "constraints": [],
        "crop_rotation": {"records": []},
        "succession_plans": {},
        "soil_tests": {},
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"app exited early with code {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"server never bound on port {port}")


def _unwrap(call) -> object:
    data = call.structuredContent
    if isinstance(data, dict) and set(data.keys()) == {"result"}:
        return data["result"]
    return data


async def drive(port: int, token: str) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client as http_client

    out: dict = {"errors": []}
    url = f"http://127.0.0.1:{port}/mcp?token={token}"
    async with http_client(url) as (r, w, _), ClientSession(r, w) as session:
            await session.initialize()

            # --- create the bed through the agent's own write path
            c = await session.call_tool(
                "create_object",
                {"object_type": "RAISED_BED", "x": 0, "y": 0, "width": 200,
                 "height": 100, "name": "Dogfood Bed"},
            )
            out["create_error"] = c.isError
            out["create_text"] = (c.content[0].text if c.content else "")[:300]
            bed_id = (_unwrap(c) or {}).get("item_id")
            if not bed_id:
                out["errors"].append(
                    f"create_object produced no item_id: {out['create_text']}"
                )
                return out
            out["bed_id"] = bed_id

            tools = await session.list_tools()
            out["tools"] = sorted(t.name for t in tools.tools)
            prompts = await session.list_prompts()
            out["prompts"] = sorted(p.name for p in prompts.prompts)

            # --- reads
            c = await session.call_tool("get_succession_plan", {"bed_id": bed_id})
            out["plan_before"] = _unwrap(c)
            out["plan_before_error"] = c.isError
            out["plan_before_text"] = (c.content[0].text if c.content else "")[:400]

            c = await session.call_tool("find_succession_gaps", {"bed_id": bed_id})
            out["gaps"] = _unwrap(c)
            out["gaps_error"] = c.isError
            out["gaps_text"] = (c.content[0].text if c.content else "")[:300]

            first = out["gaps"][0] if out["gaps"] else None
            out["suggestions"] = []
            if first:
                # Window length, used to check fits_window consistency.
                out["suggest_gap_days"] = (
                    datetime.date.fromisoformat(first["end_date"])
                    - datetime.date.fromisoformat(first["start_date"])
                ).days + 1
            if first:
                c = await session.call_tool(
                    "suggest_succession",
                    {"bed_id": bed_id, "gap_start": first["start_date"],
                     "gap_end": first["end_date"],
                     "candidates": ["Garlic", "Tomato", "Lettuce", "Radish"]},
                )
                out["suggestions"] = _unwrap(c) or []
                out["suggest_error"] = c.isError

            # --- write, READ IT BACK, undo, then delete
            # The read-back matters: `not isError` alone would pass for a tool
            # that returns success while writing nothing, or writing the wrong
            # dates, or to the wrong key. An independent review of this script
            # flagged exactly that hole.
            c = await session.call_tool("get_history", {})
            out["hist_before"] = _unwrap(c)

            entries = ([{"species_key": "allium sativum", "common_name": "Garlic",
                         "start_date": first["start_date"], "end_date": first["end_date"]}]
                       if first else [])
            # No explicit `year`: the write must resolve its year by the SAME rule
            # the reads do (today's year), or a hardcoded 2026 makes this check
            # silently vacuous from 2027 onward - the gaps would be 2027 windows
            # and the write a 2026 plan, so "the written window is no longer a
            # gap" would pass while testing nothing.
            c = await session.call_tool(
                "set_succession_plan", {"bed_id": bed_id, "entries": entries}
            )
            out["write_error"] = c.isError
            out["write_text"] = (c.content[0].text if c.content else "")[:300]
            out["write_result"] = _unwrap(c)
            out["want_entry"] = entries[0] if entries else {}
            out["filled_window"] = {
                "start_date": first["start_date"], "end_date": first["end_date"],
            } if first else {}

            # Read the plan back and confirm it is what we asked for.
            c = await session.call_tool("get_succession_plan", {"bed_id": bed_id})
            out["plan_after_write"] = _unwrap(c)
            c = await session.call_tool("find_succession_gaps", {"bed_id": bed_id})
            out["gaps_after_write"] = _unwrap(c)

            c = await session.call_tool("get_history", {})
            out["hist_after"] = _unwrap(c)

            # One `undo` must restore the pre-write state exactly.
            c = await session.call_tool("undo", {})
            out["undo_error"] = c.isError
            c = await session.call_tool("get_succession_plan", {"bed_id": bed_id})
            out["plan_after_undo"] = _unwrap(c)
            c = await session.call_tool("find_succession_gaps", {"bed_id": bed_id})
            out["gaps_after_undo"] = _unwrap(c)

            # Re-write, then delete.
            c = await session.call_tool(
                "set_succession_plan", {"bed_id": bed_id, "entries": entries}
            )
            out["rewrite_error"] = c.isError
            # Read back before deleting: if the rewrite AND the delete were both
            # no-ops, `has_plan False again` would still pass.
            c = await session.call_tool("get_succession_plan", {"bed_id": bed_id})
            out["plan_after_rewrite"] = _unwrap(c)
            c = await session.call_tool("set_succession_plan",
                                        {"bed_id": bed_id, "entries": []})
            out["delete_error"] = c.isError
            c = await session.call_tool("get_succession_plan", {"bed_id": bed_id})
            out["plan_after_delete"] = _unwrap(c)

            # --- refusals
            c = await session.call_tool(
                "set_succession_plan",
                {"bed_id": "22222222-2222-4222-8222-222222222222", "entries": entries})
            out["unknown_bed_error"] = c.isError
            out["unknown_bed_text"] = (c.content[0].text if c.content else "")[:200]

            # Dates derived from the season we are actually in, so this stays
            # meaningful in any year.
            y = out["gaps"][0]["start_date"][:4] if out["gaps"] else "2026"
            c = await session.call_tool(
                "set_succession_plan",
                {"bed_id": bed_id, "entries": [
                    {"species_key": "allium sativum", "start_date": f"{y}-06-01",
                     "end_date": f"{y}-07-15"},
                    {"species_key": "lactuca sativa", "start_date": f"{y}-07-01",
                     "end_date": f"{y}-08-01"}]})
            out["overlap_error"] = c.isError
            out["overlap_text"] = (c.content[0].text if c.content else "")[:200]

            # A refusal must leave BOTH the plan and the undo stack untouched -
            # the documented promise, and invisible to an `isError` check alone.
            # Capture the baseline HERE: by now the stack holds
            # create + write + write + delete, so comparing against the depth
            # after the FIRST write compares the wrong two moments.
            c = await session.call_tool("get_history", {})
            out["hist_before_refusals"] = _unwrap(c)
            c = await session.call_tool("get_succession_plan", {"bed_id": bed_id})
            out["plan_after_refusals"] = _unwrap(c)
            c = await session.call_tool("get_history", {})
            out["hist_after_refusals"] = _unwrap(c)

            # --- prompt, fetched TWICE: once with a plan present (so the brief
            # must carry slots and candidates) and once after the delete (so the
            # empty-plan branch is exercised too).
            # NOTE: session.get_prompt, not call_tool.
            for tag in ("with_plan", "no_plan"):
                try:
                    pr = await session.get_prompt(
                        "plan-succession", {"bed_id": bed_id})
                    msgs = getattr(pr, "messages", None) or []
                    out["prompt_" + tag] = (
                        getattr(msgs[0].content, "text", "") if msgs else "")
                except Exception as exc:  # noqa: BLE001
                    out["prompt_" + tag] = ""
                    out["errors"].append(f"get_prompt ({tag}) raised {exc!r}")
            out["prompt_text"] = out["prompt_with_plan"]
    return out


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #

class Checker:
    def __init__(self) -> None:
        self.ok = True

    def __call__(self, label: str, cond: bool, detail: str = "") -> None:
        self.ok = self.ok and bool(cond)
        print(("  OK   " if cond else "  FAIL ") + label
              + (("  -- " + detail) if detail and not cond else ""))


def run_checks(out: dict) -> bool:
    c = Checker()
    if out["errors"]:
        for e in out["errors"]:
            print("  ERROR " + e)
        c.ok = False

    if True:
        print("\n=== transport sanity ===")
        c("create_object succeeded", not out.get("create_error"), str(out.get("create_text", "")))
        c("suggest_succession did not error", not out.get("suggest_error"))
        c("gaps call did not error", not out.get("gaps_error"), str(out.get("gaps_text", "")))

        print("\n=== surface ===")
        for t in ("get_succession_plan", "find_succession_gaps",
                  "suggest_succession", "set_succession_plan"):
            c(f"{t} registered", t in out.get("tools", []))
        c("plan-succession prompt registered", "plan-succession" in out.get("prompts", []))

        print("\n=== reads ===")
        p = out.get("plan_before") or {}
        c("get_succession_plan no error", not out.get("plan_before_error"),
          str(out.get("plan_before_text", "")))
        c("has_plan False on a fresh bed", p.get("has_plan") is False)
        c("coverage 'full' with a location", p.get("coverage") == "full", str(p.get("coverage")))
        c("four season segments", [s["segment"] for s in p.get("segments", [])] ==
          ["early_spring", "late_spring", "summer", "fall"],
          str([s.get("segment") for s in p.get("segments", [])]))

        print("\n=== gaps ===")
        gaps = out.get("gaps") or []
        c("four gaps", len(gaps) == 4, f"{len(gaps)} gaps (error={out.get('gaps_error')})")
        days: list = []
        for g in gaps:
            cur, end = datetime.date.fromisoformat(g["start_date"]), datetime.date.fromisoformat(g["end_date"])
            while cur <= end:
                days.append(cur)
                cur += datetime.timedelta(days=1)
        # The declared `days` must match the range it claims, otherwise the
        # disjointness assertion below could be reading a wrong field.
        bad = [g for g in gaps
               if g["days"] != (datetime.date.fromisoformat(g["end_date"])
                                - datetime.date.fromisoformat(g["start_date"])).days + 1]
        c("each gap's `days` matches its own range", not bad, str(bad)[:200])
        c("gap days never overlap", len(days) == len(set(days)),
          f"{len(days)} expanded days vs {len(set(days))} distinct")

        # GROUND TRUTH: empty_plan() authored last_spring_frost=04-15 and
        # first_fall_frost=10-15. Derive the expected season bounds here with
        # plain date arithmetic rather than the app's own helper, so a uniform
        # off-by-N in frost handling cannot pass (the write uses the same window,
        # so a shifted window would otherwise be self-consistent and invisible).
        if gaps:
            g0 = gaps[0]["start_date"]
            yr = int(g0[:4])
            last_frost = datetime.date(yr, 4, 15)
            fall_frost = datetime.date(yr, 10, 15)
            expect_first = (last_frost - datetime.timedelta(weeks=8)).isoformat()
            expect_last = (fall_frost + datetime.timedelta(weeks=2)).isoformat()
            c("first window starts 8 weeks before last frost",
              gaps[0]["start_date"] == expect_first,
              f"{gaps[0]['start_date']} != {expect_first}")
            c("last window ends 2 weeks after first fall frost",
              gaps[-1]["end_date"] == expect_last,
              f"{gaps[-1]['end_date']} != {expect_last}")
            # Disjoint clip: the first window stops a day short of the shared
            # boundary that late_spring starts on.
            expect_first_end = (last_frost - datetime.timedelta(weeks=2)
                                - datetime.timedelta(days=1)).isoformat()
            c("first window ends a day before the boundary (disjoint clip)",
              gaps[0]["end_date"] == expect_first_end,
              f"{gaps[0]['end_date']} != {expect_first_end}")
            c("windows carry the four segment labels in order",
              [g["segment"] for g in gaps] ==
              ["early_spring", "late_spring", "summer", "fall"],
              str([g.get("segment") for g in gaps]))

        print("\n=== suggestions ===")
        s = out.get("suggestions") or []
        c("suggestions returned", len(s) > 0, f"{len(s)} suggestions")
        if s:
            c("carries species_key", bool(s[0].get("species_key")))
            # `isinstance(False, bool)` is True, so a bare type check proves
            # nothing about the fit logic. Assert the CONSISTENCY instead: a
            # candidate fits iff its maturity is known and within the window.
            gap_days = out.get("suggest_gap_days") or 0
            consistent = True
            detail = ""
            for cand in s:
                m = cand.get("days_to_maturity")
                expect = isinstance(m, int) and gap_days and m <= gap_days
                if bool(cand.get("fits_window")) != bool(expect):
                    consistent = False
                    detail = (f"{cand.get('species_key')}: fits_window="
                             f"{cand.get('fits_window')!r} but maturity={m!r} "
                             f"in a {gap_days}-day window")
                    break
            c("fits_window agrees with maturity + window", consistent, detail)
            c("at least one confirmed fit", any(x.get("fits_window") for x in s))
            # Documented order: fits first, then shortest maturity, then key.
            keyed = [(not x.get("fits_window"),
                      x.get("days_to_maturity") if isinstance(x.get("days_to_maturity"), int)
                      else 10**6,
                      x.get("species_key") or "") for x in s]
            c("results follow the documented rank order", keyed == sorted(keyed),
              str([x.get("species_key") for x in s]))
            out["top_suggestion"] = s[0].get("name")
            print(f"       top: {s[0].get('name')} (family={s[0].get('family')}, "
                  f"{s[0].get('days_to_maturity')}d, fits={s[0].get('fits_window')}) "
                  f"of {len(s)} candidates in a {gap_days}-day window")

        print("\n=== write ===")
        c("write accepted", not out.get("write_error"), str(out.get("write_text", "")))
        wr = out.get("write_result") or {}
        c("WriteResult names the action", wr.get("action") == "set_succession_plan", str(wr)[:160])

        # THE read-back: acceptance alone would pass for a tool that returns
        # success while writing nothing, or writing the wrong dates.
        pw = out.get("plan_after_write") or {}
        ents = pw.get("entries") or []
        c("plan reads back as present", pw.get("has_plan") is True, str(pw.get("has_plan")))
        c("exactly one entry stored", len(ents) == 1, f"{len(ents)} entries")
        if ents:
            want = out.get("want_entry") or {}
            c("stored species_key matches", ents[0].get("species_key") == want.get("species_key"),
              f"{ents[0].get('species_key')!r} vs {want.get('species_key')!r}")
            c("stored dates match", (ents[0].get("start_date"), ents[0].get("end_date"))
              == (want.get("start_date"), want.get("end_date")),
              f"{(ents[0].get('start_date'), ents[0].get('end_date'))!r} vs "
                  f"{(want.get('start_date'), want.get('end_date'))!r}")

        filled = out.get("filled_window") or {}
        c("the written window is no longer a gap",
          not any(g["start_date"] == filled.get("start_date")
                  and g["end_date"] == filled.get("end_date")
                  for g in (out.get("gaps_after_write") or [])))

        b = out.get("hist_before") or {}
        a = out.get("hist_after") or {}
        delta = (a.get("undo_depth") or 0) - (b.get("undo_depth") or 0)
        c("exactly ONE undo step", delta == 1,
          f"before={b.get('undo_depth')} after={a.get('undo_depth')}")
        c("undo text mentions succession",
          "uccession" in (a.get("next_undo_text") or ""), repr(a.get("next_undo_text")))

        print("\n=== undo ===")
        c("undo accepted", not out.get("undo_error"))
        pu = out.get("plan_after_undo") or {}
        c("undo removes the plan", pu.get("has_plan") is False, str(pu.get("has_plan")))
        c("undo restores the original gap set",
          len(out.get("gaps_after_undo") or []) == len(out.get("gaps") or []),
          f"{len(out.get('gaps_after_undo') or [])} vs {len(out.get('gaps') or [])}")

        print("\n=== delete ===")
        c("rewrite accepted", not out.get("rewrite_error"))
        rw = out.get("plan_after_rewrite") or {}
        c("rewrite reads back as present", rw.get("has_plan") is True, str(rw.get("has_plan")))
        c("delete accepted", not out.get("delete_error"))
        c("has_plan False again", (out.get("plan_after_delete") or {}).get("has_plan") is False)

        print("\n=== refusals ===")
        c("unknown bed refused", out.get("unknown_bed_error"), str(out.get("unknown_bed_text", "")))
        c("unknown bed says WHY", "no object with id" in (out.get("unknown_bed_text") or "").lower(),
          str(out.get("unknown_bed_text", "")))
        c("overlapping slots refused", out.get("overlap_error"), str(out.get("overlap_text", "")))
        c("overlap says WHY", "overlap" in (out.get("overlap_text") or "").lower(),
          str(out.get("overlap_text", "")))
        # The documented promise: a refusal leaves the plan AND the undo stack
        # untouched. An isError check cannot see a mutating refusal.
        pr = out.get("plan_after_refusals") or {}
        c("refusals left the plan deleted", pr.get("has_plan") is False, str(pr.get("has_plan")))
        ha = out.get("hist_after_refusals") or {}
        hb = out.get("hist_before_refusals") or {}
        c("refusals added no undo step",
          (ha.get("undo_depth") or 0) == (hb.get("undo_depth") or 0),
          f"{ha.get('undo_depth')} vs baseline {hb.get('undo_depth')}")

        print("\n=== prompt ===")
        # The empty-plan branch (fetched after the delete) must SAY there is no
        # plan; the with-plan branch must name a real ranked candidate.
        pn = out.get("prompt_no_plan") or ""
        c("empty-plan brief says so", "no succession plan" in pn.lower(), repr(pn[:100]))
        top = out.get("top_suggestion")
        pt = out.get("prompt_text") or ""
        if top:
            c("brief names the top ranked candidate", top in pt, repr(top))
        # A length test alone passes for any 41-char string. Require the CONTENT
        # a real brief must carry, which also proves the renderer received live
        # data rather than a stub.
        c("plan-succession renders", len(pt) > 200, repr(pt[:120]))
        c("prompt names the bed", out.get("bed_id", "\0") in pt, out.get("bed_id", ""))
        c("prompt carries the gap dates", bool(out.get("want_entry", {}).get("start_date") in pt),
          str(out.get("want_entry")))
        c("prompt tells the agent how to write back", "set_succession_plan" in pt)
    return c.ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(DEFAULT_EXE))
    ap.add_argument(
        "--repair",
        action="store_true",
        help="Restore the documented defaults and exit. Use if a previous run was "
             "hard-killed before it could restore settings.",
    )
    args = ap.parse_args()

    if args.repair:
        before = snapshot_settings()
        print(f"before: writes={before['writes']} port={before['port']}")
        s, _app = _app_settings()
        s.agent_api_writes_enabled = False
        s.agent_api_port = 8765

        # Also drop scratch paths an earlier, less careful run left in the MRU
        # list. Only ever this harness's own temp dirs -- never a real plan.
        def _is_scratch(path: object) -> bool:
            low = str(path).lower()
            return "ogp-dogfood" in low or "ogp-verify" in low

        kept = [f for f in s.recent_files if not _is_scratch(f)]
        if len(kept) != len(s.recent_files):
            print(f"recent_files: removed {len(s.recent_files) - len(kept)} scratch entries")
            s.recent_files = kept
        s.sync()
        print(f"repaired: writes={s.agent_api_writes_enabled} port={s.agent_api_port} "
              f"(token left as-is)")
        return 0

    exe = Path(args.exe)
    if not exe.exists():
        print("FAIL: exe not built. Run:")
        print("  venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm")
        return 2

    tmp = Path(os.environ.get("TEMP", ".")) / "ogp-dogfood"
    tmp.mkdir(parents=True, exist_ok=True)
    plan = tmp / "dogfood.ogp"
    empty_plan(plan)
    port = free_port()

    before = snapshot_settings()
    proc = None
    out: dict = {"errors": []}
    try:
        token = apply_settings(port)
        proc = subprocess.Popen([str(exe), str(plan)])
        wait_for_port(port, proc)
        out = asyncio.run(drive(port, token))
    except Exception as exc:  # noqa: BLE001 - report, never traceback-only
        out["errors"].append(f"harness error: {exc!r}")
        traceback.print_exc()
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        for line in restore_settings(before):
            print("settings: " + line)

    # Run the checks even when the harness errored: a partial result is more
    # informative than "FAIL" with no detail.
    ok = run_checks(out) and not out["errors"]
    print("\nDOGFOOD: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
