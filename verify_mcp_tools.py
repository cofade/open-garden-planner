"""Verify new Agent API domain-intelligence tools via MCP streamable-HTTP."""
import requests
import json
import sys

URL = "http://127.0.0.1:64504/mcp?token=UVCxGJyCatBeGwtprrKSh0a92rMS5ukiTqh8EahTjXE"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {label}")
    else:
        failed += 1
        print(f"  FAIL: {label} — {detail}")


def call_tool(session_headers, req_id, name, arguments):
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    resp = requests.post(URL, json=payload, headers=session_headers)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"JSON-RPC error: {data['error']}")
    return data["result"]


def main():
    # ── Step 1: Initialize ──────────────────────────────────────────────
    print("\n=== Step 1: Initialize & list tools ===")
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "verification", "version": "1.0"},
        },
    }
    resp = requests.post(URL, json=init_payload, headers=HEADERS)
    print(f"Initialize: HTTP {resp.status_code}")
    session_id = resp.headers.get("mcp-session-id", "")
    if session_id:
        HEADERS["mcp-session-id"] = session_id
        print(f"Session ID: {session_id}")

    # List tools
    list_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    resp = requests.post(URL, json=list_payload, headers=HEADERS)
    tools = resp.json()["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    print(f"Available tools ({len(tool_names)}): {tool_names}")

    for expected in ["get_history", "suggest_companions", "find_compatible_sets", "check_placement"]:
        check(f"Tool '{expected}' present", expected in tool_names)

    # ── Step 2: get_history (empty plan) ───────────────────────────────
    print("\n=== Step 2: get_history (empty plan) ===")
    result = call_tool(HEADERS, 3, "get_history", {})
    # result may be wrapped in content
    if "content" in result:
        text = result["content"][0]["text"]
        hist = json.loads(text)
    else:
        hist = result
    print(json.dumps(hist, indent=2))

    check("undo_depth == 0", hist.get("undo_depth") == 0, f"got {hist.get('undo_depth')}")
    check("redo_depth == 0", hist.get("redo_depth") == 0, f"got {hist.get('redo_depth')}")
    check("next_undo_text is None", hist.get("next_undo_text") is None, f"got {hist.get('next_undo_text')}")
    check("next_redo_text is None", hist.get("next_redo_text") is None, f"got {hist.get('next_redo_text')}")

    # ── Step 3: suggest_companions(tomato) ─────────────────────────────
    print("\n=== Step 3: suggest_companions('tomato') ===")
    result = call_tool(HEADERS, 4, "suggest_companions", {"species_key": "tomato"})
    if "content" in result:
        text = result["content"][0]["text"]
        companions = json.loads(text)
    else:
        companions = result
    print(json.dumps(companions, indent=2))

    check("Returns non-empty list", isinstance(companions, list) and len(companions) > 0,
          f"got {type(companions)} len={len(companions) if isinstance(companions, list) else 'N/A'}")

    if isinstance(companions, list) and len(companions) > 0:
        required_keys = {"species_key", "name", "reasons", "source", "score"}
        for i, entry in enumerate(companions):
            missing = required_keys - set(entry.keys())
            if missing:
                check(f"Entry {i} has all keys", False, f"missing: {missing}")
                break
        else:
            check("All entries have required keys", True)

        scores = [e.get("score", 0) for e in companions]
        check("Sorted by score descending", scores == sorted(scores, reverse=True),
              f"scores={scores}")

    # ── Step 4: find_compatible_sets ───────────────────────────────────
    print("\n=== Step 4: find_compatible_sets(['corn','bean','squash'], size=3) ===")
    result = call_tool(HEADERS, 5, "find_compatible_sets", {
        "candidates": ["corn", "bean", "squash"],
        "size": 3,
    })
    if "content" in result:
        text = result["content"][0]["text"]
        sets = json.loads(text)
    else:
        sets = result
    print(json.dumps(sets, indent=2))

    check("Returns non-empty list", isinstance(sets, list) and len(sets) > 0,
          f"got {type(sets)} len={len(sets) if isinstance(sets, list) else 'N/A'}")

    if isinstance(sets, list) and len(sets) > 0:
        required_keys = {"members", "size", "score", "coverage"}
        for i, entry in enumerate(sets):
            missing = required_keys - set(entry.keys())
            if missing:
                check(f"Set {i} has all keys", False, f"missing: {missing}")
                break
        else:
            check("All sets have required keys", True)

        # Check Three Sisters found
        three_sisters = {"corn", "bean", "squash"}
        found = any(
            three_sisters.issubset(set(e.get("members", [])))
            for e in sets
        )
        check("Three Sisters (corn, bean, squash) found", found)

    # ── Step 5: check_placement ────────────────────────────────────────
    print("\n=== Step 5: check_placement(tomato, test-bed, [basil, potato]) ===")
    result = call_tool(HEADERS, 6, "check_placement", {
        "species_key": "tomato",
        "bed_id": "test-bed",
        "bed_plants": ["basil", "potato"],
    })
    if "content" in result:
        text = result["content"][0]["text"]
        placement = json.loads(text)
    else:
        placement = result
    print(json.dumps(placement, indent=2))

    required_keys = {"species_key", "bed_id", "antagonists_present", "companions_present", "spacing_ok", "soil_ok", "overall"}
    missing = required_keys - set(placement.keys())
    check("Result has all required keys", not missing, f"missing: {missing}")

    check("species_key == 'tomato'", placement.get("species_key") == "tomato",
          f"got {placement.get('species_key')}")
    check("bed_id == 'test-bed'", placement.get("bed_id") == "test-bed",
          f"got {placement.get('bed_id')}")

    antagonists = placement.get("antagonists_present", [])
    check("'potato' in antagonists_present", "potato" in antagonists,
          f"got {antagonists}")

    companions_found = placement.get("companions_present", [])
    check("'basil' in companions_present", "basil" in companions_found,
          f"got {companions_found}")

    check("overall == 'critical'", placement.get("overall") == "critical",
          f"got {placement.get('overall')}")

    # ── Step 6: get_history again (no mutation) ────────────────────────
    print("\n=== Step 6: get_history again (should not mutate stack) ===")
    result = call_tool(HEADERS, 7, "get_history", {})
    if "content" in result:
        text = result["content"][0]["text"]
        hist2 = json.loads(text)
    else:
        hist2 = result
    print(json.dumps(hist2, indent=2))

    check("undo_depth still 0", hist2.get("undo_depth") == 0, f"got {hist2.get('undo_depth')}")
    check("redo_depth still 0", hist2.get("redo_depth") == 0, f"got {hist2.get('redo_depth')}")

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL VERIFICATIONS PASSED")
    else:
        print("SOME VERIFICATIONS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
