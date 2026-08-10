import sys

from scripts.utils import is_tty


class DummySpinner:
    """Substituto sem animação para yaspin quando não há TTY.

    A animação em si é dispensada, mas o resultado final (sucesso/erro)
    precisa continuar visível, então ok()/fail()/write() imprimem a
    mensagem em vez de descartá-la.
    """

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def ok(self, text="OK"):
        if text:
            print(text, file=sys.stderr)

    def fail(self, text="FAIL"):
        if text:
            print(text, file=sys.stderr)

    def write(self, text=""):
        if text:
            print(text, file=sys.stderr)

    def hidden(self):
        class _Ctx:
            def __enter__(self):
                pass

            def __exit__(self, *args):
                pass

        return _Ctx()


def spinner(*args, **kwargs):
    if not is_tty():
        return DummySpinner()

    # Import tardio: yaspin não é necessário fora de TTY, e evitar importá-lo
    # reduz o tempo de startup do processo — importante já que o VS Code
    # LaTeX Workshop recria o processo Python a cada Ctrl+S.
    from yaspin import yaspin

    return yaspin(*args, **kwargs)
