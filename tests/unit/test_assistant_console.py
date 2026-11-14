"""Pruebas del adaptador de consola."""

from types import SimpleNamespace
import unittest

from atlas.adapters.console import run_console


class FakeRequestFactory:
    def __init__(self):
        self.contents = []

    def create(self, content):
        self.contents.append(content)
        return SimpleNamespace(content=content)


class FakeResponder:
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return SimpleNamespace(content=f"respuesta: {request.content}")


class ConsoleAdapterTests(unittest.TestCase):
    def run_with_inputs(self, values):
        pending = iter(values)
        prompts = []
        output = []

        def input_fn(prompt):
            prompts.append(prompt)
            value = next(pending)
            if isinstance(value, Exception):
                raise value
            return value

        factory = FakeRequestFactory()
        responder = FakeResponder()
        run_console(
            responder,
            factory,
            input_fn=input_fn,
            output_fn=output.append,
        )
        return factory, responder, prompts, output

    def test_processes_multiple_messages_until_exit(self):
        factory, responder, prompts, output = self.run_with_inputs(
            ["Hola", "¿Qué puedes hacer?", "salir"]
        )

        self.assertEqual(factory.contents, ["Hola", "¿Qué puedes hacer?"])
        self.assertEqual(len(responder.requests), 2)
        self.assertEqual(prompts, ["Tú> ", "Tú> ", "Tú> "])
        self.assertEqual(output[1:], [
            "Atlas> respuesta: Hola",
            "Atlas> respuesta: ¿Qué puedes hacer?",
            "Atlas: hasta luego.",
        ])

    def test_ignores_empty_messages(self):
        factory, responder, _, output = self.run_with_inputs(
            ["", "   ", "Hola", "exit"]
        )

        self.assertEqual(factory.contents, ["Hola"])
        self.assertEqual(len(responder.requests), 1)
        self.assertEqual(output[1], "Atlas> respuesta: Hola")

    def test_accepts_exit_command_case_insensitively(self):
        factory, responder, _, output = self.run_with_inputs(["SALIR"])

        self.assertEqual(factory.contents, [])
        self.assertEqual(responder.requests, [])
        self.assertEqual(output[-1], "Atlas: hasta luego.")

    def test_finishes_gracefully_on_eof(self):
        factory, responder, _, output = self.run_with_inputs([EOFError()])

        self.assertEqual(factory.contents, [])
        self.assertEqual(responder.requests, [])
        self.assertEqual(output[-1], "Atlas: sesión finalizada.")


if __name__ == "__main__":
    unittest.main()
