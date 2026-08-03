import pytest

from classes import task as task_module
from classes.task import CleanBuild, CopyTree, FnTask, RenderTemplate, Task


class FakeTemplate:
    def __init__(self, text):
        self.text = text

    def render(self, **context):
        return self.text.format(**context)


def test_clean_build_removes_matching_files(tmp_path, monkeypatch):
    monkeypatch.setattr(task_module, "BUILD_DIR", tmp_path)
    (tmp_path / "main.pdf").write_text("pdf")
    (tmp_path / "main.log").write_text("log")
    (tmp_path / "keep.txt").write_text("keep")

    CleanBuild().run()

    remaining = {p.name for p in tmp_path.iterdir()}
    assert remaining == {"keep.txt"}


def test_render_template_writes_rendered_output(tmp_path):
    output = tmp_path / "out.tex"
    render = RenderTemplate(
        template=FakeTemplate("Olá, {name}!"),
        context={"name": "Mundo"},
        output=output,
    )
    render.run()
    assert output.read_text(encoding="utf-8") == "Olá, Mundo!"


def test_copy_tree_copies_single_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo")
    dst = tmp_path / "dst" / "src.txt"

    CopyTree(src=src, dst=dst).run()

    assert dst.read_text(encoding="utf-8") == "conteúdo"


def test_copy_tree_ignores_tex_files_outside_whitelist(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    (src_dir / "chapter1.tex").write_text("ignored")
    (src_dir / "glossaries.tex").write_text("kept")
    (src_dir / "notes.txt").write_text("kept too")

    CopyTree(src=src_dir, dst=dst_dir, ignore_tex=True).run()

    copied = {p.name for p in dst_dir.iterdir()}
    assert copied == {"glossaries.tex", "notes.txt"}


def test_copy_tree_whitelist_applies_in_nested_subdirectories(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    sub_dir = src_dir / "chapters"
    sub_dir.mkdir(parents=True)
    (sub_dir / "chapter1.tex").write_text("ignored")
    (sub_dir / "glossaries.tex").write_text("kept")

    CopyTree(src=src_dir, dst=dst_dir, ignore_tex=True).run()

    copied = {p.name for p in (dst_dir / "chapters").iterdir()}
    assert copied == {"glossaries.tex"}


def test_copy_tree_dst_inside_src_respects_whitelist(tmp_path):
    src_dir = tmp_path / "project"
    dst_dir = src_dir / "build"
    src_dir.mkdir()
    (src_dir / "chapter1.tex").write_text("ignored")
    (src_dir / "glossaries.tex").write_text("kept")

    CopyTree(src=src_dir, dst=dst_dir, ignore_tex=True).run()

    copied = {p.name for p in dst_dir.iterdir()}
    assert copied == {"glossaries.tex"}


def test_copy_tree_rejects_unsupported_source_type():
    with pytest.raises(TypeError):
        CopyTree(src="not-a-path-or-traversable", dst=None).run()


def test_fn_task_calls_function_with_args_and_kwargs():
    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))

    FnTask(record, 1, 2, key="value").run()

    assert calls == [((1, 2), {"key": "value"})]


def test_runner_executes_chain_tasks_in_dependency_order():
    order = []

    first = FnTask(lambda: order.append("first"), mode="chain")
    second = FnTask(lambda: order.append("second"), mode="chain", dependencies=[first])
    third = FnTask(lambda: order.append("third"), mode="chain", dependencies=[second])

    Task.runner([third, first, second])

    assert order == ["first", "second", "third"]


def test_runner_raises_on_circular_dependency():
    a = FnTask(lambda: None, mode="chain")
    b = FnTask(lambda: None, mode="chain", dependencies=[a])
    a.dependencies = [b]

    with pytest.raises(RuntimeError):
        Task.runner([a, b])
