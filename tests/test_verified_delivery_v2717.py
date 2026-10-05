"""Compatibility tests: verified delivery moved into the mission runtime in 2.8.0."""
from olympus.agent.mission_compiler import MissionCompiler
from olympus.agent.acceptance import compile_contract, ExactTextFile


def test_exact_contract_is_compiled_into_mission_profile(tmp_path):
    compiled = MissionCompiler().compile(
        "Crie um arquivo chamado teste.txt contendo apenas: OLYMPUS_OK"
    )
    assert compiled.exact_text_artifact == ("teste.txt", "OLYMPUS_OK")
    assert compiled.task_family == "file_operation"


def test_exact_contract_is_a_runtime_acceptance_check(tmp_path):
    contract = compile_contract(
        "Crie um arquivo chamado teste.txt contendo apenas: OLYMPUS_OK",
        tmp_path,
    )
    assert any(isinstance(check, ExactTextFile) for check in contract.checks)


def test_acceptance_reads_disk_instead_of_model_finish(tmp_path):
    task = "Crie um arquivo chamado teste.txt contendo apenas: OLYMPUS_OK"
    contract = compile_contract(task, tmp_path)
    contract.prepare()
    (tmp_path / "teste.txt").write_text("OLYMPIUS_OK\n", encoding="utf-8")
    results, _ = contract.verify(("teste.txt",))
    assert any(not result.passed for result in results)
    (tmp_path / "teste.txt").write_text("OLYMPUS_OK\n", encoding="utf-8")
    results, _ = contract.verify(("teste.txt",))
    assert all(result.passed for result in results)
