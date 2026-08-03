from yaspin import yaspin

from scripts.utils import is_tty


class DummySpinner:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def ok(self, *_):
        pass

    def fail(self, *_):
        pass

    def write(self, *_):
        pass

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
    return yaspin(*args, **kwargs)
