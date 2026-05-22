"""Paper Space / Print Layout package (Phase 13 Package B — US-B7).

A paper-space layout holds one printable page composed of one viewport
(rendering a region of the model-space canvas), a title block, and a
scale bar. The MVP supports exactly one layout per project; multi-page
and multi-viewport layouts are explicitly out of scope.
"""

from .page_sizes import (
    A3,
    A4,
    DEFAULT_ORIENTATION,
    DEFAULT_PAGE_NAME,
    LETTER,
    PAGE_SIZES,
    PageSize,
    get_page,
    page_size_cm,
)
from .paper_space_scene import PaperSpaceScene
from .paper_space_view import PaperSpaceView
from .scale_bar_item import ScaleBarItem
from .title_block_item import TitleBlockItem
from .viewport_item import ViewportItem

__all__ = [
    "A3",
    "A4",
    "DEFAULT_ORIENTATION",
    "DEFAULT_PAGE_NAME",
    "LETTER",
    "PAGE_SIZES",
    "PageSize",
    "PaperSpaceScene",
    "PaperSpaceView",
    "ScaleBarItem",
    "TitleBlockItem",
    "ViewportItem",
    "get_page",
    "page_size_cm",
]
