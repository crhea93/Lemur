"""Saving figures: a PNG for reports and a vector PDF beside it for the paper.

Text, lines and markers in the PDF stay sharp at any zoom. Images drawn with
``imshow`` are embedded at ``dpi``; galleries of model inputs (144-252 px each)
pass a lower value, since more pixels there only add file size.
"""

from pathlib import Path

DPI = 300


def save_figure(fig, path, dpi=DPI):
    """Write ``path`` (PNG) and the same figure as ``path`` with a .pdf suffix."""
    path = Path(path)
    fig.savefig(path, dpi=dpi)
    fig.savefig(path.with_suffix(".pdf"), dpi=dpi)
