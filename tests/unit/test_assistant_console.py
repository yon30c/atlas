"""Pruebas del adaptador de consola desacoplado de la aplicación."""

from types import SimpleNamespace
import unittest

from atlas.adapters.console import run_console


class FakeRuntime:
    def __init__(self):
        self.contents = []

    def respond(self, content):
        self.contents.append(content)
        return SimpleNamespace(content=f"respuesta: {content}")


class ConsoleAdapterTests(unittest.TestCase):
    def run_with_inputs(self, values):
        pending = iter(values)
        prompts = []
        output = []

        def input_fn(prompt):
            prompts.append(prompt)
            value = next(pending)
            if isinstance(value, BaseException):
                raise value
            return value

        runtime = FakeRuntime()
        run_console(
            runtime,
            input_fn=input_fn,
            output_fn=output.append,
        )
        return runtime, prompts, output

    def test_processes_multiple_messages_until_exit(self):
        runtime, prompts, output = self.run_with_inputs(
            ["Hola", "¿Qué puedes hacer?", "salir"]
        )

        self.assertEqual(runtime.contents, ["Hola", "¿Qué puedes hacer?"])
        self.assertEqual(prompts, ["Tú> ", "Tú> ", "Tú> "])
        self.assertEqual(output[1:], [
            "Atlas> respuesta: Hola",
            "Atlas> respuesta: ¿Qué puedes hacer?",
            "Atlas: hasta luego.",
        ])

    def test_ignores_empty_messages(self):
        runtime, _, output = self.run_with_inputs(["", "   ", "Hola", "exit"])

        self.assertEqual(runtime.contents, ["Hola"])
        self.assertEqual(output[1], "Atlas> respuesta: Hola")

    def test_accepts_exit_command_case_insensitively(self):
        runtime, _, output = self.run_with_inputs(["SALIR"])

        self.assertEqual(runtime.contents, [])
        self.assertEqual(output[-1], "Atlas: hasta luego.")

    def test_slash_exit_command(self):
        runtime, _, output = self.run_with_inputs(["/EXIT"])

        self.assertEqual(runtime.contents, [])
        self.assertEqual(output[-1], "Atlas: hasta luego.")

    def test_help_command_is_case_insensitive_and_does_not_call_runtime(self):
        runtime, _, output = self.run_with_inputs(["/HELP", "/exit"])

        self.assertEqual(runtime.contents, [])
        self.assertIn("/help", output[1])
        self.assertIn("/clear", output[1])
        self.assertIn("/exit", output[1])

    def test_clear_clears_screen_without_clearing_conversation(self):
        pending = iter(["Hola", "/clear", "¿Recuerdas mi mensaje?", "/exit"])
        output = []
        writes = []
        runtime = FakeRuntime()

        run_console(
            runtime,
            input_fn=lambda prompt: next(pending),
            output_fn=output.append,
            write_fn=writes.append,
        )

        self.assertEqual(writes, ["\033[2J\033[H"])
        self.assertEqual(
            runtime.contents,
            ["Hola", "¿Recuerdas mi mensaje?"],
        )
        self.assertIn("Atlas> respuesta: Hola", output)
        self.assertIn("Atlas> respuesta: ¿Recuerdas mi mensaje?", output)

    def test_finishes_gracefully_on_eof(self):
        runtime, _, output = self.run_with_inputs([EOFError()])

        self.assertEqual(runtime.contents, [])
        self.assertEqual(output[-1], "Atlas: sesión finalizada.")

    def test_finishes_gracefully_on_keyboard_interrupt(self):
        runtime, _, output = self.run_with_inputs([KeyboardInterrupt()])

        self.assertEqual(runtime.contents, [])
        self.assertEqual(
            output[-1],
            "Atlas: interrupción recibida. Sesión finalizada.",
        )


if __name__ == "__main__":
    unittest.main()
