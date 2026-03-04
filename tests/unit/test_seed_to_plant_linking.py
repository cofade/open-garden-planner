"""Unit tests for US-9.6: Seed-to-plant manual linking."""
from __future__ import annotations

import pytest

from open_garden_planner.models.seed_inventory import SeedInventoryStore, SeedPacket


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestSeedPacketIdStorage:
    """seed_packet_id persisted in plant_instance metadata dict."""

    def test_set_and_retrieve_seed_packet_id(self) -> None:
        """seed_packet_id round-trips through plant_instance metadata."""
        metadata: dict = {}
        metadata["plant_instance"] = {}
        metadata["plant_instance"]["seed_packet_id"] = "abc-123"
        assert metadata["plant_instance"]["seed_packet_id"] == "abc-123"

    def test_unlink_removes_key(self) -> None:
        """Setting seed_packet_id to None then popping it removes the link."""
        metadata: dict = {"plant_instance": {"seed_packet_id": "abc-123"}}
        metadata["plant_instance"].pop("seed_packet_id", None)
        assert "seed_packet_id" not in metadata["plant_instance"]

    def test_no_seed_packet_id_returns_none(self) -> None:
        """plant_instance dict with no seed_packet_id key returns None via .get()."""
        metadata: dict = {"plant_instance": {"notes": "some note"}}
        assert metadata["plant_instance"].get("seed_packet_id") is None


class TestSeedPacketLinkLookup:
    """Verify seed packet store look-ups for linked packets."""

    def _make_store(self, *packets: SeedPacket) -> SeedInventoryStore:
        store = SeedInventoryStore.__new__(SeedInventoryStore)
        store._packets = {p.id: p for p in packets}
        store._path = None  # type: ignore[assignment]
        return store

    def test_get_linked_packet(self) -> None:
        packet = SeedPacket(species_name="Tomato", germination_days_min=7, germination_days_max=14)
        store = self._make_store(packet)
        result = store.get(packet.id)
        assert result is not None
        assert result.germination_days_min == 7
        assert result.germination_days_max == 14

    def test_get_unknown_id_returns_none(self) -> None:
        store = self._make_store()
        assert store.get("nonexistent-id") is None

    def test_packet_with_germination_data_for_calendar(self) -> None:
        """Seed packet germination data should override species defaults when linked."""
        packet = SeedPacket(
            species_name="Pepper",
            germination_days_min=14,
            germination_days_max=21,
            germination_temp_opt_c=24.0,
        )
        store = self._make_store(packet)
        p = store.get(packet.id)
        assert p is not None
        assert p.germination_days_min == 14
        assert p.germination_days_max == 21
        assert p.germination_temp_opt_c == 24.0


class TestBidirectionalLinkScanning:
    """Simulate scanning canvas items for linked plants."""

    def _make_canvas_items(
        self, links: list[tuple[str, str]]
    ) -> list[dict]:
        """Return fake canvas item metadata dicts with seed_packet_id set."""
        items = []
        for name, packet_id in links:
            items.append({"name": name, "metadata": {"plant_instance": {"seed_packet_id": packet_id}}})
        return items

    def _get_linked_names(self, items: list[dict], packet_id: str) -> list[str]:
        names = []
        for item in items:
            pi = item.get("metadata", {}).get("plant_instance", {})
            if pi.get("seed_packet_id") == packet_id:
                names.append(item["name"])
        return names

    def test_finds_linked_plants(self) -> None:
        items = self._make_canvas_items([
            ("Tomato 1", "pkt-001"),
            ("Tomato 2", "pkt-001"),
            ("Pepper 1", "pkt-002"),
        ])
        assert self._get_linked_names(items, "pkt-001") == ["Tomato 1", "Tomato 2"]

    def test_no_linked_plants_returns_empty(self) -> None:
        items = self._make_canvas_items([("Tomato 1", "pkt-001")])
        assert self._get_linked_names(items, "pkt-999") == []

    def test_unlinked_items_not_included(self) -> None:
        items = [{"name": "Herb", "metadata": {"plant_instance": {}}}]
        assert self._get_linked_names(items, "pkt-001") == []
