import shutil
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Literal, Iterable, Union
from importlib.abc import Traversable
from configs.paths import BUILD_DIR

Mode = Literal["thread", "process", "chain"]
Dependencies = Iterable["Task"] | None
Source = Union[Path, Traversable]

class Task(ABC):
    
    name: str
    mode: Mode
    dependencies: Dependencies
    
    def __init__(
        self,  dependencies: Dependencies, mode: Mode = "chain"
    ):
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
                t for t in remaining
                if all(dep in completed for dep in (t.dependencies or []))
            ]
            if not ready:
                raise RuntimeError("Dependências circulares detectadas.")

            # ------- chain -------
            chain_tasks = [t for t in ready if t.mode == "chain"]
            if len(ready) == 1 and chain_tasks:
                t = chain_tasks[0]

                start = time.perf_counter()
                with yaspin(Spinners.dots, text=f"{icon(t)} {t.name}", color="cyan") as sp:
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

                        with yaspin(Spinners.dots, text=f"{icon(t)} {t.name}", color="yellow") as sp:
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
                    async_results = [(t, pool.apply_async(t.run)) for t in process_tasks]

                    for t, result in async_results:
                        start = time.perf_counter()

                        with yaspin(Spinners.dots, text=f"{icon(t)} {t.name}", color="green") as sp:
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
        dependencies: Dependencies = None
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
        dependencies: Dependencies = None
    ):
        super().__init__(mode=mode, dependencies=dependencies)
        self.src = src
        self.dst = dst
        self.ignore_tex = ignore_tex

    def run(self) -> None:
        # 1. Se a origem for um objeto Traversable (recurso empacotado)
        if isinstance(self.src, Traversable):
            # Usamos a função auxiliar para copiar recursos
            self.copy_traversable_recursively_delegate(self.src, self.dst)
            
        # 2. Se a origem for um Path (caminho físico no disco - modo de desenvolvimento)
        elif isinstance(self.src, Path):
            
            # Código de cópia de arquivo único (original)
            if self.src.is_file():
                if self.ignore_tex and self.src.suffix == ".tex":
                    return
                # Certifica que o destino existe se for um arquivo
                self.dst.parent.mkdir(parents=True, exist_ok=True) 
                shutil.copy2(self.src, self.dst)
                return

            # Código de cópia de diretório (original)
            shutil.copytree(
                self.src,
                self.dst,
                dirs_exist_ok=True,
                # Usa o 'ignore_patterns' para arquivos em disco
                ignore=shutil.ignore_patterns("*.tex") if self.ignore_tex else None
            )

        else:
             raise TypeError(f"Tipo de origem não suportado: {type(self.src)}")

    def copy_traversable_recursively_delegate(self, src_traversable: Traversable, dst_path: Path):
        """Copia recursivamente, delegando sub-diretórios para novas CopyTree Tasks."""
    
        # 1. Cria o diretório de destino
        dst_path.mkdir(parents=True, exist_ok=True)

        for item in src_traversable.iterdir():
            item_dst = dst_path / item.name
            
            if item.is_file():
                if self.ignore_tex and item.name.endswith(".tex"):
                    continue
                
                with item.open('rb') as src_file:
                    with item_dst.open('wb') as dst_file:
                        shutil.copyfileobj(src_file, dst_file)
                        
            elif item.is_dir():
                # CHAVE: Criar uma nova instância de CopyTree para o subdiretório
                # O novo item é a nova origem, e item_dst é o novo destino.
                # Não é mais uma chamada de método, mas uma nova Task.
                
                # CUIDADO: Se você estiver executando isso dentro de um thread, 
                # a nova Task não será executada imediatamente, mas sim agendada.
                
                # Se for para execução síncrona/imediata (melhor para recursão):
                new_copy_task = CopyTree(
                    src=item, # Novo Traversable (o subdiretório)
                    dst=item_dst, # Novo Path de destino
                    ignore_tex=self.ignore_tex,
                    mode="chain" # Força a execução síncrona se o runner for multi-threaded
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
        **kwargs
    ):
        super().__init__(mode=mode, dependencies=dependencies)
        self.fn = fn
        self.args = args
        self.kw = kwargs

    def run(self):
        self.fn(*self.args, **self.kw)