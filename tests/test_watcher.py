from pathlib import Path

from watchfiles import Change

from scripts import watcher
from scripts.watcher import (
    BUILD_FAILED,
    BUILD_OK,
    BUILD_STARTED,
    DEBOUNCE_MS,
    watch,
    watch_filter,
    watch_paths,
)


def _template(tmp_path: Path) -> tuple[Path, Path]:
    template_dir = tmp_path / "tpl"
    template_dir.mkdir()
    (template_dir / "main.tex").write_text("x")
    data = template_dir / "input.json"
    data.write_text("{}")
    return data, template_dir


def _fake_watcher(batches, calls=None):
    """Imita watchfiles.watch: registra os argumentos e devolve lotes já
    "debounceados" de mudanças, um por rebuild esperado."""

    def fake(*paths, **kwargs):
        if calls is not None:
            calls.append((paths, kwargs))
        yield from batches

    return fake


def test_initial_build_then_one_rebuild_per_batch(tmp_path):
    data, template_dir = _template(tmp_path)
    builds = []

    batches = [
        {(Change.modified, str(data))},
        # rajada de eventos agrupada pelo debounce = um rebuild só
        {(Change.modified, str(template_dir / "main.tex")), (Change.added, str(template_dir / "style.sty"))},
    ]
    watch(
        str(data),
        str(template_dir),
        "tectonic",
        rebuild=lambda *args: builds.append(args) or True,
        watcher=_fake_watcher(batches),
    )

    assert builds == [(str(data), str(template_dir), "tectonic")] * 3


def test_watcher_receives_paths_filter_and_debounce(tmp_path):
    data, template_dir = _template(tmp_path)
    calls = []

    watch(str(data), str(template_dir), rebuild=lambda *_a: True, watcher=_fake_watcher([], calls))

    (paths, kwargs) = calls[0]
    assert paths[0] == template_dir
    assert kwargs["debounce"] == DEBOUNCE_MS == 300
    assert kwargs["raise_interrupt"] is False
    assert kwargs["watch_filter"] is not None


def test_failed_build_does_not_stop_watching(tmp_path, capsys):
    data, template_dir = _template(tmp_path)
    results = iter([False, True])
    builds = []

    def flaky(*args):
        builds.append(args)
        if len(builds) == 2:
            raise RuntimeError("compilação explodiu")
        return next(results)

    batches = [{(Change.modified, str(data))}, {(Change.modified, str(data))}]
    watch(str(data), str(template_dir), rebuild=flaky, watcher=_fake_watcher(batches))

    assert len(builds) == 3
    err = capsys.readouterr().err
    assert err.count(BUILD_STARTED) == 3
    assert err.count(BUILD_FAILED) == 2
    assert err.count(BUILD_OK) == 1
    assert "compilação explodiu" in err


def test_ctrl_c_during_build_exits_cleanly(tmp_path, capsys):
    data, template_dir = _template(tmp_path)

    def interrupted(*_args):
        raise KeyboardInterrupt

    watch(str(data), str(template_dir), rebuild=interrupted, watcher=_fake_watcher([]))

    assert "Watch encerrado" in capsys.readouterr().err


def test_build_markers_wrap_each_build(tmp_path, capsys):
    data, template_dir = _template(tmp_path)

    watch(str(data), str(template_dir), rebuild=lambda *_a: True, watcher=_fake_watcher([]))

    lines = capsys.readouterr().err.splitlines()
    assert lines.index(BUILD_STARTED) < lines.index(BUILD_OK)


def test_watch_paths_add_external_data_file(tmp_path):
    _, template_dir = _template(tmp_path)
    outside = tmp_path / "dados.json"

    paths = watch_paths(outside, template_dir)

    assert paths[:2] == [template_dir, outside]


def test_watch_paths_skip_data_file_inside_template(tmp_path):
    data, template_dir = _template(tmp_path)

    assert data not in watch_paths(data, template_dir)


def test_watch_paths_include_real_asset_dirs(tmp_path, monkeypatch):
    data, template_dir = _template(tmp_path)
    assets = tmp_path / "assets"
    (assets / "images").mkdir(parents=True)
    (assets / "plots").mkdir()
    monkeypatch.setattr(watcher.res, "files", lambda _pkg: assets)

    assert watch_paths(data, template_dir) == [template_dir, assets / "images", assets / "plots"]


def test_filter_ignores_build_output_and_vscode(tmp_path):
    _, template_dir = _template(tmp_path)
    f = watch_filter()

    assert f(Change.modified, str(template_dir / "main.tex"))
    assert f(Change.modified, str(template_dir / "src" / "intro.tex"))
    assert not f(Change.modified, str(template_dir / "build" / "main.pdf"))
    assert not f(Change.added, str(template_dir / "build" / "images" / "a.png"))
    assert not f(Change.modified, str(template_dir / ".vscode" / "settings.json"))
    assert not f(Change.modified, str(template_dir / ".main.tex.swp"))


def test_watch_paths_skip_assets_in_frozen_binary(tmp_path, monkeypatch):
    data, template_dir = _template(tmp_path)
    assets = tmp_path / "assets"
    (assets / "images").mkdir(parents=True)
    monkeypatch.setattr(watcher.res, "files", lambda _pkg: assets)
    monkeypatch.setattr(watcher.sys, "frozen", True, raising=False)

    assert watch_paths(data, template_dir) == [template_dir]
