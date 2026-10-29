import ctypes
import os
import sys
from unittest.mock import patch

import pytest

from open_garden_planner.ui.view3d.quick3d.adapter_info import (
    _enum_adapters_dxgi,
    _is_hardware_adapter,
    _safe_release_com,
    detect_is_software,
    has_hardware_adapter,
    is_software_adapter_name,
)


class TestSoftwareAdapterNameMatching:
    @pytest.mark.parametrize(
        "name",
        [
            "Microsoft Basic Render Driver",
            "microsoft basic render driver",
            "WARP",
            "Microsoft WARP",
            "llvmpipe (LLVM 15.0.7, 256 bits)",
            "Mesa llvmpipe",
            "Software Rasterizer Device",
            "Standard Software Rasterizer",
        ],
    )
    def test_software_adapter_names(self, name: str) -> None:
        assert is_software_adapter_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            "NVIDIA GeForce RTX 4070",
            "AMD Radeon RX 7900 XTX",
            "Intel(R) Arc(TM) A770 Graphics",
            "Apple M2 Pro",
            None,
            "",
            "   ",
        ],
    )
    def test_hardware_and_empty_adapter_names(self, name: str | None) -> None:
        assert not is_software_adapter_name(name)


class TestIsHardwareAdapter:
    @pytest.mark.parametrize(
        ("desc", "flags"),
        [
            ("NVIDIA GeForce RTX 4070", 0),
            # Integrated GPU / APUs with shared memory report vram=0 but valid hardware
            ("Intel(R) Iris(R) Xe Graphics", 0),
            ("Intel(R) UHD Graphics 770", 0),
            ("AMD Radeon(TM) Graphics", 0),
            # Non-software flag bits like DXGI_ADAPTER_FLAG_REMOTE (1) must not disqualify hardware
            ("NVIDIA RTX A5000", 1),
        ],
    )
    def test_hardware_adapters_accepted(self, desc: str, flags: int) -> None:
        assert _is_hardware_adapter(desc, flags)

    @pytest.mark.parametrize(
        ("desc", "flags"),
        [
            # Software rasterizers by name
            ("Microsoft Basic Render Driver", 0),
            ("Microsoft WARP", 0),
            ("Mesa llvmpipe", 0),
            # Software rasterizers by flag (DXGI_ADAPTER_FLAG_SOFTWARE = 2)
            ("Generic Display Adapter", 2),
            ("Custom Rasterizer", 3),  # bit 1 set
        ],
    )
    def test_software_adapters_rejected(self, desc: str, flags: int) -> None:
        assert not _is_hardware_adapter(desc, flags)


class TestEnvironmentVariablePrecedence:
    def test_qsg_env_var_forces_software(self) -> None:
        with patch.dict(os.environ, {"QSG_RHI_PREFER_SOFTWARE_RENDERER": "1"}, clear=True):
            assert not has_hardware_adapter()
            assert detect_is_software()

    def test_libgl_env_var_forces_software(self) -> None:
        with patch.dict(os.environ, {"LIBGL_ALWAYS_SOFTWARE": "1"}, clear=True):
            assert not has_hardware_adapter()
            assert detect_is_software()

    def test_detect_is_software_follows_hardware_check(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "open_garden_planner.ui.view3d.quick3d.adapter_info.has_hardware_adapter",
                return_value=False,
            ),
        ):
            assert detect_is_software()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "open_garden_planner.ui.view3d.quick3d.adapter_info.has_hardware_adapter",
                return_value=True,
            ),
        ):
            assert not detect_is_software()


class TestPlatformAndDxgiInspection:
    def test_non_windows_platform_assumes_hardware(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys, "platform", "linux"),
        ):
            assert has_hardware_adapter()

    @pytest.mark.parametrize(
        ("mock_adapters", "expected_has_hw"),
        [
            ([("NVIDIA GeForce RTX 4070", 0)], True),
            ([("Intel(R) Iris(R) Xe Graphics", 0)], True),
            ([("Microsoft Basic Render Driver", 0)], False),
            ([("Microsoft WARP", 0), ("NVIDIA GeForce RTX 4070", 0)], True),
            ([("Generic Rasterizer", 2)], False),
            ([], False),
            (None, True),  # COM failure fallback
        ],
    )
    def test_has_hardware_adapter_enumeration_results(
        self, mock_adapters: list[tuple[str, int]] | None, expected_has_hw: bool
    ) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys, "platform", "win32"),
            patch(
                "open_garden_planner.ui.view3d.quick3d.adapter_info._enum_adapters_dxgi",
                return_value=mock_adapters,
            ),
        ):
            assert has_hardware_adapter() is expected_has_hw

    def test_real_dxgi_enumeration_on_windows(self) -> None:
        if sys.platform != "win32":
            pytest.skip("Windows DXGI inspection test")
        adapters = _enum_adapters_dxgi()
        # When DXGI works on Windows, it returns a list of adapters
        if adapters is not None:
            assert isinstance(adapters, list)
            assert len(adapters) > 0
            desc, flags = adapters[0]
            assert isinstance(desc, str)
            assert isinstance(flags, int)

    def test_safe_release_com_handles_none_and_null_ptrs(self) -> None:
        _safe_release_com(None)
        null_ptr = ctypes.c_void_p(0)
        _safe_release_com(null_ptr)
        fake_obj = object()
        _safe_release_com(fake_obj)

    def test_enum_adapters_dxgi_logs_debug_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        with (
            patch.object(sys, "platform", "win32"),
            patch("ctypes.windll", create=True) as mock_windll,
            caplog.at_level(logging.DEBUG),
        ):
            mock_windll.dxgi.CreateDXGIFactory1.return_value = 0x887A0001
            result = _enum_adapters_dxgi()
            assert result is None
            assert "DXGIFactory1 creation failed" in caplog.text
