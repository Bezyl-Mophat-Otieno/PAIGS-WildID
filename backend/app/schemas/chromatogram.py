from typing import Dict, List

from pydantic import BaseModel


class ChromatogramResult(BaseModel):
    """Raw AB1 chromatogram/peak data for one read (forward or reverse).

    channel_order: the base each of the four fluorescence channels
    represents, in the order this file's own FWO_1 tag gives them (e.g.
    ["G", "A", "T", "C"]) -- never assumed, since ABIF allows it to vary.
    trace: base letter -> that channel's raw fluorescence intensity at
    every sample point across the whole read. num_samples: the trace's
    length (same for every channel). peak_locations: for each called
    base, the sample index in `trace` where its peak was detected.
    base_calls: the base-called sequence itself, same length and order
    as peak_locations, so base_calls[i] was called at peak_locations[i].
    """

    channel_order: List[str]
    trace: Dict[str, List[int]]
    num_samples: int
    peak_locations: List[int]
    base_calls: str
