import json
import logging

import pytest

from buscajus.core.logging import configurar_logging


def test_emite_uma_linha_json_com_campos_extras(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logging("INFO")
    logging.getLogger("buscajus.teste").info("caderno processado", extra={"acordaos_aceitos": 3})

    evento = json.loads(capsys.readouterr().out.strip())
    assert evento["msg"] == "caderno processado"
    assert evento["nivel"] == "INFO"
    assert evento["logger"] == "buscajus.teste"
    assert evento["acordaos_aceitos"] == 3


def test_desliga_log_de_acesso_do_uvicorn() -> None:
    configurar_logging("INFO")
    assert logging.getLogger("uvicorn.access").disabled
