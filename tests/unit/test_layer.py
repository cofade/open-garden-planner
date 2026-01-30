"""Tests for the Layer model."""

from uuid import UUID

import pytest

from open_garden_planner.models.layer import Layer, create_default_layers


def test_layer_creation():
    """Test creating a layer with default values."""
    layer = Layer(name="Test Layer")

    assert layer.name == "Test Layer"
    assert layer.visible is True
    assert layer.locked is False
    assert layer.opacity == 1.0
    assert layer.z_order == 0
    assert isinstance(layer.id, UUID)


def test_layer_serialization():
    """Test layer serialization to dict."""
    layer = Layer(name="My Layer", visible=False, locked=True, opacity=0.5, z_order=3)

    data = layer.to_dict()

    assert data["name"] == "My Layer"
    assert data["visible"] is False
    assert data["locked"] is True
    assert data["opacity"] == 0.5
    assert data["z_order"] == 3
    assert "id" in data
    assert isinstance(data["id"], str)


def test_layer_deserialization():
    """Test layer deserialization from dict."""
    layer_id = "550e8400-e29b-41d4-a716-446655440000"
    data = {
        "id": layer_id,
        "name": "Restored Layer",
        "visible": False,
        "locked": True,
        "opacity": 0.75,
        "z_order": 2,
    }

    layer = Layer.from_dict(data)

    assert str(layer.id) == layer_id
    assert layer.name == "Restored Layer"
    assert layer.visible is False
    assert layer.locked is True
    assert layer.opacity == 0.75
    assert layer.z_order == 2


def test_layer_roundtrip():
    """Test that serialization and deserialization are inverse operations."""
    original = Layer(name="Roundtrip", visible=False, opacity=0.3, z_order=5)
    data = original.to_dict()
    restored = Layer.from_dict(data)

    assert str(restored.id) == str(original.id)
    assert restored.name == original.name
    assert restored.visible == original.visible
    assert restored.locked == original.locked
    assert restored.opacity == original.opacity
    assert restored.z_order == original.z_order


def test_create_default_layers():
    """Test creation of default layers."""
    layers = create_default_layers()

    assert len(layers) == 1
    assert layers[0].name == "Layer 1"
    assert layers[0].z_order == 0
    assert layers[0].visible is True
    assert layers[0].locked is False
