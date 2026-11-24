import pytest

from assist.window import TranscriptWindow


def test_window_keeps_newest_segments_in_order():
    window = TranscriptWindow(max_segments=2)
    for segment in ["old", " middle ", "latest"]:
        window.add(segment)
    assert window.text() == "middle\nlatest"


def test_blank_segments_do_not_evict_speech():
    window = TranscriptWindow(max_segments=1)
    assert window.text() == ""
    window.add("spoken")
    window.add(" \n ")
    assert window.text() == "spoken"


@pytest.mark.parametrize("size", [0, -1])
def test_window_rejects_nonpositive_capacity(size):
    with pytest.raises(ValueError):
        TranscriptWindow(max_segments=size)
