# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Shared code for the Cartopy_file project; see ``docs/cartopy_file/index.md``."""

from __future__ import annotations

from .data import (
    configure_cartopy,
    natural_earth_paths,
    prepare_matplotlib_env,
    project_root,
    shared_data_dir,
)
from .fonts import CJK_FONT, FALLBACK_FONT, LATIN_FONT, apply_matplotlib_fonts
from .output import SVG_SUFFIX, apply_svg_output, save_svg

__all__ = [
    "CJK_FONT",
    "FALLBACK_FONT",
    "LATIN_FONT",
    "SVG_SUFFIX",
    "apply_matplotlib_fonts",
    "apply_svg_output",
    "configure_cartopy",
    "natural_earth_paths",
    "prepare_matplotlib_env",
    "project_root",
    "save_svg",
    "shared_data_dir",
]
