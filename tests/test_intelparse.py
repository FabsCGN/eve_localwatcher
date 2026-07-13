"""Intel-line parsing against real-world fixture lines + chatlog tailing."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eve_localwatcher import intelparse, mapdata
from eve_localwatcher.chatlog import ChatlogTail

SYNTH = {
    "systems": {"10": ["K7D-II", -0.2], "11": ["N-M1A3", -0.3],
                "12": ["P-ZMZV", -0.1], "13": ["49-U6U", -0.4],
                "14": ["V-LEKM", -0.2]},
    "adj": {"10": [11, 12], "11": [10], "12": [10, 13], "13": [12],
            "14": []},
}
BUBBLE = {10: 0, 11: 1, 12: 1, 13: 2}   # V-LEKM (14) is OUT of range


@pytest.fixture(autouse=True)
def synth_graph():
    saved = (mapdata._names, mapdata._by_lower, mapdata._adj, mapdata._failed)
    mapdata._install(SYNTH)
    yield
    mapdata._names, mapdata._by_lower, mapdata._adj, mapdata._failed = saved


def _report(msg):
    return intelparse.extract_report(msg, datetime.now(timezone.utc), BUBBLE)


def test_parse_line_real_format():
    ts, author, msg = intelparse.parse_line(
        "[ 2026.07.11 20:28:00 ] Ju Hee > N-M1A3*  Cj Allyn")
    assert (ts.year, ts.hour, ts.second) == (2026, 20, 0)
    assert author == "Ju Hee"
    assert msg == "N-M1A3*  Cj Allyn"


def test_parse_line_rejects_motd():
    assert intelparse.parse_line("      Channel Name:    Foo Intel") is None
    assert intelparse.parse_line("") is None


def test_system_with_star_and_multiword_pilot():
    r = _report("N-M1A3*  Cj Allyn")
    assert r.system_name == "N-M1A3"
    assert r.pilot_candidates == ["Cj Allyn"]


def test_multiword_name_survives_system_in_the_middle():
    r = _report("Chani Crendraven  K7D-II  Aleeera")
    assert r.system_name == "K7D-II"
    assert r.pilot_candidates == ["Chani Crendraven", "Aleeera"]


def test_prefix_system_and_status_words():
    r = _report("https://dscan.info/v/fc3 in P-Z gate, bunch of dessies w bubble")
    assert r.system_name == "P-ZMZV"
    assert r.pilot_candidates == []      # chatter must not become names


def test_out_of_range_system_ignored():
    assert _report("V-LEKM +9 EVE-RO / Goonswarm Federation") is None


def test_chatter_ignored():
    for msg in ("clr.", "GG guys", "eyes ?", "On a ping off the keep"):
        assert _report(msg) is None


def test_no_system_no_report():
    assert _report("Aleeera Cheetah") is None


def test_chatlog_tail_reads_appended_utf16(tmp_path: Path):
    f = tmp_path / "MyIntel_20260712_000000_123.txt"
    f.write_bytes("﻿header\r\n".encode("utf-16-le"))
    tail = ChatlogTail(tmp_path, "MyIntel")
    assert tail.current_file == f
    assert tail.poll() == []                       # starts at EOF
    with open(f, "ab") as fh:
        fh.write("[ 2026.07.12 10:00:00 ] A > K7D-II Foo\r\n"
                 .encode("utf-16-le"))
    lines = tail.poll()
    assert lines == ["[ 2026.07.12 10:00:00 ] A > K7D-II Foo"]
    with open(f, "ab") as fh:                      # partial line buffering
        fh.write("[ 2026.07.12 10:00:05 ] B > half".encode("utf-16-le"))
    assert tail.poll() == []
    with open(f, "ab") as fh:
        fh.write(" done\r\n".encode("utf-16-le"))
    assert tail.poll() == ["[ 2026.07.12 10:00:05 ] B > half done"]
