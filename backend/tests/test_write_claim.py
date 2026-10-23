"""Unverified-write banner: only real claims, not a description of the rule."""

from agent_window.agent.loop import _looks_like_write_claim

_INTRO = (
    "你好！我是这个 workspace 里的编码助手，工作目录是 `/home/caapap/agent window`"
    "（Loop Agent 仓库根目录）。\n"
    "我不会声称「已改好」或「测试通过」——只有工具结果真的显示 applied 或成功时，才算数。"
)


def test_intro_that_quotes_the_rule_is_not_a_write_claim() -> None:
    assert _looks_like_write_claim(_INTRO) is False
    assert _looks_like_write_claim("不要声称测试通过") is False
    assert _looks_like_write_claim("并没有已创建文件") is False


def test_asserted_write_or_green_tests_still_count() -> None:
    assert _looks_like_write_claim("测试通过") is True
    assert _looks_like_write_claim("已创建 README.md") is True
    assert _looks_like_write_claim("pytest 结果 12 passed") is True
    assert _looks_like_write_claim("刚才已创建，所以不用再写") is False
    assert _looks_like_write_claim("区别在于测试通过才算完成") is True
