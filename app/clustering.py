"""Circular defect-echo clustering for coil ultrasonic scanning.

The scan head reports echo positions in millimetres along the coil
circumference ``L``.  A defect sitting on the zero seam of the
circumference shows up as two groups of echoes (one just below ``L``,
one just above ``0``); this module merges such split groups back into
unique defect clusters.

Pipeline
--------
1. Echoes sharing the same position are collapsed, keeping the largest
   amplitude only.
2. Remaining echoes are merged whenever the circular distance between
   neighbours is ``<= G`` (the wrap distance from the last point back to
   the first point counts as well).  If every neighbour distance is
   ``<= G`` all echoes form a single cluster.
3. Each cluster is linearised by cutting the circle at its largest
   internal gap (ties: the gap whose end position is numerically
   largest).  The echo right after the cut is the cluster start, which
   makes normal clusters start at their minimum position and gives
   zero-crossing clusters a stable start on the high side of the seam.
4. Cluster length is measured along the circumference in positive
   direction from the start to the last point; the peak is the largest
   amplitude (ties: smallest position).  Clusters are returned sorted
   by start ascending.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class Echo:
    """Single echo in millimetre units."""

    position: float
    amplitude: float


@dataclass(frozen=True)
class Cluster:
    """Unique defect cluster on the circumference."""

    start: float
    length: float
    echo_count: int
    peak_amplitude: float
    peak_position: float


def dedupe_by_position(echoes: Iterable[Echo]) -> List[Echo]:
    """Keep only the strongest echo per position, sorted by position."""
    best: Dict[float, float] = {}
    for echo in echoes:
        current = best.get(echo.position)
        if current is None or echo.amplitude > current:
            best[echo.position] = echo.amplitude
    return [Echo(position=p, amplitude=a) for p, a in sorted(best.items())]


def _circular_gaps(positions: Sequence[float], L: float) -> List[float]:
    """Distance from every point to the next one in positive direction.

    ``positions`` must be sorted ascending; the final entry is the wrap
    distance from the last point back to the first one across zero.
    """
    n = len(positions)
    gaps = [positions[i + 1] - positions[i] for i in range(n - 1)]
    gaps.append(L - positions[-1] + positions[0])
    return gaps


def _groups(positions: Sequence[float], L: float, G: float) -> List[List[int]]:
    """Index groups of echoes whose circular neighbour distance is <= G.

    A gap strictly larger than ``G`` breaks the circle; the arcs between
    consecutive breaks are the clusters.  With no break at all, every
    echo belongs to one single cluster.
    """
    n = len(positions)
    gaps = _circular_gaps(positions, L)
    breaks = [i for i, gap in enumerate(gaps) if gap > G]
    if not breaks:
        return [list(range(n))]
    groups: List[List[int]] = []
    for k, brk in enumerate(breaks):
        nxt = breaks[k + 1] if k + 1 < len(breaks) else breaks[0] + n
        groups.append([(brk + 1 + j) % n for j in range(nxt - brk)])
    return groups


def _summarize(members: Sequence[Echo], L: float) -> Cluster:
    """Describe one cluster; ``members`` must be sorted by position."""
    pos = [e.position for e in members]
    m = len(pos)
    gaps = _circular_gaps(pos, L)
    # Cut the circle at the largest gap; on ties pick the gap whose end
    # position is numerically largest.  The echo right after the cut is
    # the cluster start and the length is the remaining arc.
    cut = 0
    for i in range(1, m):
        end_i = pos[(i + 1) % m]
        end_cut = pos[(cut + 1) % m]
        if gaps[i] > gaps[cut] or (gaps[i] == gaps[cut] and end_i > end_cut):
            cut = i
    start = pos[(cut + 1) % m]
    length = L - gaps[cut]
    peak_amplitude = max(e.amplitude for e in members)
    peak_position = min(e.position for e in members if e.amplitude == peak_amplitude)
    return Cluster(
        start=start,
        length=length,
        echo_count=m,
        peak_amplitude=peak_amplitude,
        peak_position=peak_position,
    )


def cluster_echoes(L: float, G: float, echoes: Iterable[Echo]) -> List[Cluster]:
    """Merge echoes into unique defect clusters, sorted by start ascending."""
    unique = dedupe_by_position(echoes)
    positions = [e.position for e in unique]
    clusters = [
        _summarize(sorted((unique[i] for i in group), key=lambda e: e.position), L)
        for group in _groups(positions, L, G)
    ]
    clusters.sort(key=lambda c: c.start)
    return clusters
