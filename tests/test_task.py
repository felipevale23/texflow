import os
import time
from pathlib import Path

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


def test_render_template_preserves_mtime_when_content_unchanged(tmp_path):
    output = tmp_path / "out.tex"
    render = RenderTemplate(
        template=FakeTemplate("Olá, {name}!"),
        context={"name": "Mundo"},
        output=output,
    )
    render.run()
    original_mtime = output.stat().st_mtime_ns

    # Garante que o próximo write, se acontecer, teria um mtime diferente.
    time.sleep(0.01)
    render.run()

    assert output.stat().st_mtime_ns == original_mtime


def test_render_template_rewrites_when_content_changes(tmp_path):
    output = tmp_path / "out.tex"
    render = RenderTemplate(
        template=FakeTemplate("Olá, {name}!"),
        context={"name": "Mundo"},
        output=output,
    )
    render.run()

    render.context = {"name": "Outro"}
    render.run()

    assert output.read_text(encoding="utf-8") == "Olá, Outro!"


def test_copy_tree_copies_single_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo")
    dst = tmp_path / "dst" / "src.txt"

    CopyTree(src=src, dst=dst).run()

    assert dst.read_text(encoding="utf-8") == "conteúdo"


def test_copy_tree_skips_write_when_content_unchanged(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo")
    dst = tmp_path / "dst" / "src.txt"

    CopyTree(src=src, dst=dst).run()
    original_mtime = dst.stat().st_mtime_ns

    time.sleep(0.01)
    CopyTree(src=src, dst=dst).run()

    assert dst.stat().st_mtime_ns == original_mtime


def test_copy_tree_rewrites_when_content_changes(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo")
    dst = tmp_path / "dst" / "src.txt"

    CopyTree(src=src, dst=dst).run()

    src.write_text("outro conteúdo")
    CopyTree(src=src, dst=dst).run()

    assert dst.read_text(encoding="utf-8") == "outro conteúdo"


def test_copy_tree_directory_skips_unchanged_files(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    (src_dir / "keep.txt").write_text("mesmo conteúdo")

    CopyTree(src=src_dir, dst=dst_dir).run()
    original_mtime = (dst_dir / "keep.txt").stat().st_mtime_ns

    time.sleep(0.01)
    CopyTree(src=src_dir, dst=dst_dir).run()

    assert (dst_dir / "keep.txt").stat().st_mtime_ns == original_mtime


def test_copy_tree_symlink_mode_links_single_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo")
    dst = tmp_path / "dst" / "src.txt"

    CopyTree(src=src, dst=dst, symlink=True).run()

    assert dst.is_symlink()
    assert dst.resolve() == src.resolve()
    assert dst.read_text(encoding="utf-8") == "conteúdo"


def test_copy_tree_symlink_mode_links_directory_contents(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    (src_dir / "image.png").write_text("dados binários")

    CopyTree(src=src_dir, dst=dst_dir, symlink=True).run()

    linked = dst_dir / "image.png"
    assert linked.is_symlink()
    assert linked.resolve() == (src_dir / "image.png").resolve()


def test_copy_tree_symlink_mode_skips_when_already_linked(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo")
    dst = tmp_path / "dst" / "src.txt"

    CopyTree(src=src, dst=dst, symlink=True).run()
    original_target = os.readlink(dst)

    CopyTree(src=src, dst=dst, symlink=True).run()

    assert os.readlink(dst) == original_target


def test_copy_tree_symlink_mode_replaces_stale_regular_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo novo")
    dst = tmp_path / "dst" / "src.txt"
    dst.parent.mkdir(parents=True)
    dst.write_text("conteúdo velho de uma cópia física antiga")

    CopyTree(src=src, dst=dst, symlink=True).run()

    assert dst.is_symlink()
    assert dst.read_text(encoding="utf-8") == "conteúdo novo"


def test_copy_tree_symlink_mode_falls_back_to_copy_when_unsupported(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    src.write_text("conteúdo")
    dst = tmp_path / "dst" / "src.txt"
    dst.parent.mkdir(parents=True)

    def boom(self, target):
        raise OSError("symlink não suportado")

    monkeypatch.setattr(Path, "symlink_to", boom)

    CopyTree(src=src, dst=dst, symlink=True).run()

    assert not dst.is_symlink()
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
