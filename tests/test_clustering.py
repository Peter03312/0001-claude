"""Boundary tests for the circular clustering algorithm."""

from app.clustering import Cluster, Echo, cluster_echoes, dedupe_by_position


def test_dedupe_keeps_strongest_echo_per_position():
    echoes = [
        Echo(10.0, 50.0),
        Echo(10.0, 80.0),
        Echo(10.0, 60.0),
        Echo(20.0, 40.0),
    ]
    assert dedupe_by_position(echoes) == [Echo(10.0, 80.0), Echo(20.0, 40.0)]


def test_dedupe_reduces_echo_count_before_merging():
    echoes = [Echo(100.0, 50.0), Echo(100.0, 70.0), Echo(110.0, 60.0)]
    clusters = cluster_echoes(L=500.0, G=20.0, echoes=echoes)
    assert clusters == [
        Cluster(start=100.0, length=10.0, echo_count=2, peak_amplitude=70.0, peak_position=100.0)
    ]


def test_gap_equal_to_G_merges():
    # Boundary is inclusive: distance == G must merge.
    clusters = cluster_echoes(L=100.0, G=10.0, echoes=[Echo(10.0, 1.0), Echo(20.0, 2.0)])
    assert clusters == [
        Cluster(start=10.0, length=10.0, echo_count=2, peak_amplitude=2.0, peak_position=20.0)
    ]


def test_gap_just_above_G_splits():
    echoes = [Echo(10.0, 1.0), Echo(20.0, 2.0), Echo(31.0, 3.0)]
    clusters = cluster_echoes(L=100.0, G=10.0, echoes=echoes)
    assert [c.start for c in clusters] == [10.0, 31.0]
    assert clusters[0].echo_count == 2
    assert clusters[1].echo_count == 1
    assert clusters[1].length == 0.0


def test_zero_G_splits_everything():
    echoes = [Echo(10.0, 1.0), Echo(20.0, 2.0)]
    clusters = cluster_echoes(L=100.0, G=0.0, echoes=echoes)
    assert [c.start for c in clusters] == [10.0, 20.0]
    assert all(c.echo_count == 1 and c.length == 0.0 for c in clusters)


def test_wrap_gap_equal_to_G_merges_across_zero():
    # The last-to-first distance counts and the boundary is inclusive.
    clusters = cluster_echoes(L=360.0, G=10.0, echoes=[Echo(355.0, 5.0), Echo(5.0, 7.0)])
    assert clusters == [
        Cluster(start=355.0, length=10.0, echo_count=2, peak_amplitude=7.0, peak_position=5.0)
    ]


def test_zero_crossing_cluster_start_length_and_peak():
    echoes = [
        Echo(350.0, 40.0),
        Echo(355.0, 60.0),
        Echo(10.0, 55.0),
        Echo(20.0, 50.0),
    ]
    clusters = cluster_echoes(L=360.0, G=15.0, echoes=echoes)
    assert clusters == [
        Cluster(start=350.0, length=30.0, echo_count=4, peak_amplitude=60.0, peak_position=355.0)
    ]


def test_zero_crossing_and_normal_cluster_sorted_by_start():
    echoes = [Echo(350.0, 5.0), Echo(5.0, 6.0), Echo(100.0, 7.0), Echo(110.0, 8.0)]
    clusters = cluster_echoes(L=360.0, G=15.0, echoes=echoes)
    assert [c.start for c in clusters] == [100.0, 350.0]
    assert clusters[0].length == 10.0
    assert clusters[1].length == 15.0
    assert clusters[1].peak_position == 5.0  # peak follows the strongest echo


def test_all_gaps_within_G_form_single_cluster():
    # Every neighbour distance (including the wrap) is <= G: one cluster,
    # started right after the largest gap (here the wrap gap 110).
    echoes = [Echo(100.0, 1.0), Echo(200.0, 2.0), Echo(300.0, 3.0), Echo(350.0, 4.0)]
    clusters = cluster_echoes(L=360.0, G=120.0, echoes=echoes)
    assert clusters == [
        Cluster(start=100.0, length=250.0, echo_count=4, peak_amplitude=4.0, peak_position=350.0)
    ]


def test_all_one_cluster_cut_at_largest_linear_gap():
    # Largest gap (190) is not the wrap gap: the cluster starts after it.
    echoes = [Echo(10.0, 1.0), Echo(200.0, 2.0), Echo(210.0, 3.0)]
    clusters = cluster_echoes(L=360.0, G=200.0, echoes=echoes)
    assert clusters == [
        Cluster(start=200.0, length=170.0, echo_count=3, peak_amplitude=3.0, peak_position=210.0)
    ]


def test_largest_gap_tie_prefers_largest_end_position():
    # Four identical gaps of 100: the gap ending at 350 wins, so the
    # cluster starts at 350.
    echoes = [Echo(50.0, 1.0), Echo(150.0, 2.0), Echo(250.0, 3.0), Echo(350.0, 4.0)]
    clusters = cluster_echoes(L=400.0, G=120.0, echoes=echoes)
    assert len(clusters) == 1
    assert clusters[0].start == 350.0
    assert clusters[0].length == 300.0


def test_normal_cluster_starts_at_min_position():
    echoes = [Echo(100.0, 1.0), Echo(110.0, 2.0), Echo(120.0, 3.0), Echo(300.0, 4.0)]
    clusters = cluster_echoes(L=360.0, G=15.0, echoes=echoes)
    assert [c.start for c in clusters] == [100.0, 300.0]
    assert clusters[0].length == 20.0
    assert clusters[1].length == 0.0


def test_single_echo_forms_zero_length_cluster():
    clusters = cluster_echoes(L=360.0, G=10.0, echoes=[Echo(42.0, 9.0)])
    assert clusters == [
        Cluster(start=42.0, length=0.0, echo_count=1, peak_amplitude=9.0, peak_position=42.0)
    ]


def test_peak_amplitude_tie_prefers_smallest_position():
    echoes = [Echo(350.0, 90.0), Echo(10.0, 90.0)]
    clusters = cluster_echoes(L=360.0, G=30.0, echoes=echoes)
    assert len(clusters) == 1
    assert clusters[0].peak_amplitude == 90.0
    assert clusters[0].peak_position == 10.0


def test_fractional_positions_and_boundary():
    echoes = [Echo(0.2, 1.0), Echo(0.8, 2.0)]
    clusters = cluster_echoes(L=1.0, G=0.4, echoes=echoes)
    # wrap distance 0.4 == G merges across zero
    assert len(clusters) == 1
    assert clusters[0].start == 0.8
    assert abs(clusters[0].length - 0.4) < 1e-12
