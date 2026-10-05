import unittest

from olympus.agent.new_target_resolver import (
    NewTargetResolutionError,
    resolve_new_target,
)


class TestNewTargetResolver(unittest.TestCase):

    def test_function(self):
        self.assertEqual(
            resolve_new_target(
                "Crie uma função chamada calcular_media"
            ),
            "olympus/agent/calcular_media.py",
        )

    def test_python_function(self):
        self.assertEqual(
            resolve_new_target(
                "Crie uma função Python chamada converter_temperatura"
            ),
            "olympus/agent/converter_temperatura.py",
        )

    def test_class(self):
        self.assertEqual(
            resolve_new_target(
                "Crie uma classe chamada Cliente"
            ),
            "olympus/agent/cliente.py",
        )

    def test_ambiguous_task_is_blocked(self):
        with self.assertRaises(
            NewTargetResolutionError
        ):
            resolve_new_target(
                "Melhore o sistema de autenticação"
            )


if __name__ == "__main__":
    unittest.main()
