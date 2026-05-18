from harp.input import IncrementalTyper


class FakeTyper:
    """Records ops; emulates a screen buffer for assertions."""

    def __init__(self):
        self.screen = ""

    def backspace(self, count: int) -> None:
        if count > 0:
            self.screen = self.screen[:-count]

    def type_text(self, text: str) -> None:
        self.screen += text

    def filter_text(self, text: str) -> str:
        return text


def test_append_only_growth():
    f = FakeTyper()
    it = IncrementalTyper(f)
    it.update("the quick")
    it.update("the quick brown")
    assert f.screen == "the quick brown"


def test_backpatch_rewrites_divergent_tail():
    f = FakeTyper()
    it = IncrementalTyper(f)
    it.update("the kwik brown")
    it.update("the quick brown")
    assert f.screen == "the quick brown"


def test_minimal_diff_preserves_common_prefix():
    f = FakeTyper()
    it = IncrementalTyper(f)
    it.update("hello world")
    f.type_text("")
    ops = []
    f.backspace = lambda c, ops=ops: ops.append(("bs", c)) or None
    f.type_text = lambda t, ops=ops: ops.append(("tt", t)) or None
    it.update("hello there")
    assert ops == [("bs", 5), ("tt", "there")]


def test_backspace_cap_falls_back_to_append_only():
    f = FakeTyper()
    it = IncrementalTyper(f, max_backspaces=3)
    it.update("aaaa bbbb cccc")
    it.update("xxxx")
    assert f.screen == "aaaa bbbb ccccxxxx"
    assert it.append_only is True


def test_pause_defers_until_safe():
    f = FakeTyper()
    paused = {"v": True}
    it = IncrementalTyper(f, is_paused=lambda: paused["v"])
    it.update("typed while user busy")
    assert f.screen == ""
    paused["v"] = False
    it.update("typed while user busy now")
    assert f.screen == "typed while user busy now"
