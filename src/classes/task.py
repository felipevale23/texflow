import shutil
from abc import ABC, abstractmethod
from collections.abc import Iterable
from importlib.abc import Traversable
from pathlib import Path
from typing import Literal

from configs.paths import BUILD_DIR

Mode = Literal["thread", "process", "chain"]
Dependencies = Iterable["Task"] | None
Source = Path | Traversable


class Task(ABC):
    name: str
    mode: Mode
    dependencies: Dependencies

    def __init__(self, dependencies: Dependencies, mode: Mode = "chain"):
        self.mode = mode
        self.dependencies = dependencies or None

    @abstractmethod
    def run(self) -> None:
        pass

    def __call__(self) -> None:
        self.run()

    @classmethod
    def runner(cls, tasks: list["Task"]):
        import time

        from yaspin import yaspin
        from yaspin.spinners import Spinners

        TASK_ICONS = {
            "clean-build": "🧹",
            "render-template": "📝",
            "copy-tree": "📦",
            "fn-task": "🧪",
            "thread": "🧵",
            "process": "🔀",
            "chain": "🔗",
            "default": "⚙",
        }

        completed = set()
        remaining = set(tasks)

        def icon(t):
            return TASK_ICONS.get(t.name, TASK_ICONS.get(t.mode, TASK_ICONS["default"]))

        while remaining:
            ready = [
                t
                for t in remaining
                if all(dep in completed for dep in (t.dependencies or []))
            ]
            if not ready:
                raise RuntimeError("Dependências circulares detectadas.")

            # ------- chain -------
            chain_tasks = [t for t in ready if t.mode == "chain"]
            if len(ready) == 1 and chain_tasks:
                t = chain_tasks[0]

                start = time.perf_counter()
                with yaspin(
                    Spinners.dots, text=f"{icon(t)} {t.name}", color="cyan"
                ) as sp:
                    t.run()
                    end = time.perf_counter()
                    sp.ok(f"✔ ({end - start:.2f}s)")

                completed.add(t)
                remaining.remove(t)
                continue

            # ------- thread -------
            thread_tasks = [t for t in ready if t.mode == "thread"]
            if thread_tasks:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_map = {executor.submit(t.run): t for t in thread_tasks}

                    for future in concurrent.futures.as_completed(future_map):
                        t = future_map[future]
                        start = time.perf_counter()

                        with yaspin(
                            Spinners.dots, text=f"{icon(t)} {t.name}", color="yellow"
                        ) as sp:
                            future.result()
                            end = time.perf_counter()
                            sp.ok(f"✔ ({end - start:.2f}s)")

                        completed.add(t)
                        remaining.remove(t)

            # ------- process -------
            process_tasks = [t for t in ready if t.mode == "process"]
            if process_tasks:
                import multiprocessing

                with multiprocessing.Pool() as pool:
                    async_results = [
                        (t, pool.apply_async(t.run)) for t in process_tasks
                    ]

                    for t, result in async_results:
                        start = time.perf_counter()

                        with yaspin(
                            Spinners.dots, text=f"{icon(t)} {t.name}", color="green"
                        ) as sp:
                            result.get()
                            end = time.perf_counter()
                            sp.ok(f"✔ ({end - start:.2f}s)")

                        completed.add(t)
                        remaining.remove(t)


class CleanBuild(Task):
    name = "clean-build"

    def __init__(self, *, mode: Mode = "thread", dependencies: Dependencies = None):
        super().__init__(mode=mode, dependencies=dependencies)

    def run(self) -> None:
        for file in BUILD_DIR.glob("main.*"):
            try:
                file.unlink()
            except PermissionError:
                print(f"Não foi possível remover {file}")


class RenderTemplate(Task):
    name = "render-template"

    def __init__(
        self,
        template,
        context: dict,
        output: Path,
        *,
        mode: Mode = "thread",
        dependencies: Dependencies = None,
    ):
        super().__init__(mode=mode, dependencies=dependencies)
        self.template = template
        self.context = context
        self.output = output

    def run(self) -> None:
        rendered = self.template.render(**self.context)
        self.output.write_text(rendered, encoding="utf-8")


class CopyTree(Task):
    name = "copy-tree"

    def __init__(
        self,
        src: Source,
        dst: Path,
        ignore_tex=False,
        *,
        mode: Mode = "thread",
        dependencies: Dependencies = None,
    ):
        super().__init__(mode=mode, dependencies=dependencies)
        self.src = src
        self.dst = dst
        self.ignore_tex = ignore_tex

    def run(self) -> None:
        # 1. Se a origem for um Path (caminho físico no disco - modo de desenvolvimento)
        # CUIDADO: Path também satisfaz o protocolo estrutural de Traversable
        # (possui iterdir/is_dir/is_file/open), então este check precisa vir
        # ANTES do isinstance(Traversable) abaixo, ou nunca será alcançado.
        if isinstance(self.src, Path):
            # Código de cópia de arquivo único (original)
            if self.src.is_file():
                if self.ignore_tex and self.src.suffix == ".tex":
                    return
                # Certifica que o destino existe se for um arquivo
                self.dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.src, self.dst)
                return

            # 🔥 Arquivos .tex que DEVEM ser copiados mesmo com ignore_tex=True
            tex_whitelist = {"glossaries.tex", "abstract.tex", "conclusions.tex"}
            excluded_names = {"build", "__pycache__", ".git"}

            src = self.src.resolve()
            dst = self.dst.resolve()

            def should_ignore(path: Path) -> bool:
                # Evita o loop infinito garantindo que a pasta de destino
                # jamais seja copiada para dentro dela mesma.
                if path.resolve() == dst:
                    return True

                if path.name in excluded_names:
                    return True

                if self.ignore_tex and path.suffix == ".tex":
                    if path.name in tex_whitelist:
                        print(f"✅ LIBERADO: {path.name}")
                        return False  # Não ignora se estiver na whitelist
                    print(
                        f"🚫 IGNORADO: {path.name} (não está na whitelist {tex_whitelist})"
                    )
                    return True  # Ignora os demais

                return False

            # Callback compatível com shutil.copytree(ignore=...), reutilizado
            # em todas as cópias para que a whitelist valha também nas
            # subpastas e no caso normal (dst fora de src).
            def ignore(directory, names):
                base = Path(directory)
                return {name for name in names if should_ignore(base / name)}

            # 🔥 CASO ESPECIAL: dst dentro de src
            if dst.is_relative_to(src):
                dst.mkdir(parents=True, exist_ok=True)

                for item in src.iterdir():
                    if should_ignore(item):
                        continue

                    target = dst / item.name

                    if item.is_dir():
                        shutil.copytree(item, target, dirs_exist_ok=True, ignore=ignore)
                    else:
                        shutil.copy2(item, target)

            # 🚀 CASO NORMAL
            else:
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)

        # 2. Se a origem for um objeto Traversable não-Path (recurso empacotado)
        elif isinstance(self.src, Traversable):
            self.copy_traversable_recursively_delegate(self.src, self.dst)

        else:
            raise TypeError(f"Tipo de origem não suportado: {type(self.src)}")

    def copy_traversable_recursively_delegate(
        self, src_traversable: Traversable, dst_path: Path
    ):
        """Copia recursivamente, delegando sub-diretórios para novas CopyTree Tasks."""

        # 1. Cria o diretório de destino
        dst_path.mkdir(parents=True, exist_ok=True)

        for item in src_traversable.iterdir():
            # 🔥 CORREÇÃO 3: Bloqueia as pastas indesejadas também no modo Traversable
            if item.name in ("build", "__pycache__", ".git"):
                continue

            item_dst = dst_path / item.name

            if item.is_file():
                if self.ignore_tex and item.name.endswith(".tex"):
                    continue

                with item.open("rb") as src_file, item_dst.open("wb") as dst_file:
                    shutil.copyfileobj(src_file, dst_file)

            elif item.is_dir():
                # CHAVE: Criar uma nova instância de CopyTree para o subdiretório
                # O novo item é a nova origem, e item_dst é o novo destino.
                # Não é mais uma chamada de método, mas uma nova Task.

                # CUIDADO: Se você estiver executando isso dentro de um thread,
                # a nova Task não será executada imediatamente, mas sim agendada.

                # Se for para execução síncrona/imediata (melhor para recursão):
                new_copy_task = CopyTree(
                    src=item, dst=item_dst, ignore_tex=self.ignore_tex, mode="chain"
                )

                # Executa a nova sub-tarefa imediatamente
                new_copy_task.run()


class FnTask(Task):
    name = "fn-task"

    def __init__(
        self,
        fn,
        *args,
        mode: Mode = "thread",
        dependencies: Dependencies = None,
        **kwargs,
    ):
        super().__init__(mode=mode, dependencies=dependencies)
        self.fn = fn
        self.args = args
        self.kw = kwargs

    def run(self):
        self.fn(*self.args, **self.kw)
