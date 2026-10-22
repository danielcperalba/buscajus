from datetime import date

import pytest
from pydantic import ValidationError

from buscajus.core.config import Config


def test_configuracao_padrao_e_valida() -> None:
    config = Config()
    assert config.djen.tribunais == ["TJPR"]
    assert config.djen.inicio_ementas["TJPR"] == date(2025, 7, 23)
    assert config.tjdft.tamanho_pagina == 40


def test_le_campos_aninhados_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSCAJUS_DJEN__TRIBUNAIS", '["tjpr", "TJSC"]')
    monkeypatch.setenv(
        "BUSCAJUS_DJEN__INICIO_EMENTAS", '{"TJPR": "2025-07-23", "tjsc": "2024-01-02"}'
    )
    config = Config()
    assert config.djen.tribunais == ["TJPR", "TJSC"]
    assert config.djen.inicio_ementas["TJSC"] == date(2024, 1, 2)


def test_rejeita_tjdft_no_djen_com_conector_proprio_ativo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSCAJUS_DJEN__TRIBUNAIS", '["TJPR", "TJDFT"]')
    monkeypatch.setenv(
        "BUSCAJUS_DJEN__INICIO_EMENTAS", '{"TJPR": "2025-07-23", "TJDFT": "2024-01-01"}'
    )
    with pytest.raises(ValidationError, match="TJDFT não pode ser coletado pelo DJEN"):
        Config()


def test_aceita_tjdft_no_djen_se_conector_proprio_desativado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BUSCAJUS_DJEN__TRIBUNAIS", '["TJDFT"]')
    monkeypatch.setenv("BUSCAJUS_DJEN__INICIO_EMENTAS", '{"TJDFT": "2024-01-01"}')
    monkeypatch.setenv("BUSCAJUS_TJDFT__ATIVO", "false")
    assert Config().djen.tribunais == ["TJDFT"]


def test_exige_data_de_inicio_das_ementas_por_tribunal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSCAJUS_DJEN__TRIBUNAIS", '["TJPR", "TJSC"]')
    with pytest.raises(ValidationError, match="TJSC"):
        Config()


def test_rejeita_pagina_do_tjdft_maior_que_40(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSCAJUS_TJDFT__TAMANHO_PAGINA", "50")
    with pytest.raises(ValidationError, match="tamanho_pagina"):
        Config()
