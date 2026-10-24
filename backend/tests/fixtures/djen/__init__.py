"""Gerador das fixtures sintéticas do caderno do DJEN (F1-02).

Os arquivos desta pasta são gerados a partir de ``dados.py``. Para regerar (de ``backend/tests``)::

    uv run python -m fixtures.djen

Um teste confere que os arquivos versionados batem com o gerador.
"""

import hashlib
import io
import json
import zipfile
from html.entities import codepoint2name
from pathlib import Path
from typing import Any

from fixtures.djen import dados

PASTA = Path(__file__).parent
ITENS_POR_ARQUIVO = 10
URL_ZIP = (
    "https://djen-prd.prd.s3.cnj.jus.br/cadernos/{tribunal}/{data}/v{versao}/caderno.zip"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=300&X-Amz-Signature=assinatura-ficticia"
)
FUSO = "-03:00"


def numero_cnj(
    sequencial: int, ano: int = 2099, justica: int = 8, tribunal: int = 16, origem: int = 9999
) -> tuple[str, str]:
    """Número CNJ fictício (ano 2099, origem 9999) com dígito verificador válido."""
    base = f"{sequencial:07d}{ano:04d}{justica}{tribunal:02d}{origem:04d}"
    dv = 98 - int(base + "00") % 97
    digitos = f"{sequencial:07d}{dv:02d}{ano:04d}{justica}{tribunal:02d}{origem:04d}"
    mascara = f"{sequencial:07d}-{dv:02d}.{ano:04d}.{justica}.{tribunal:02d}.{origem:04d}"
    return digitos, mascara


def entidades(texto: str, *, numericas: bool = False) -> str:
    """Codifica todo caractere não ASCII como entidade HTML, como no ``texto`` do DJEN."""
    saida = []
    for caractere in texto:
        codigo = ord(caractere)
        if codigo < 128:
            saida.append(caractere)
        elif not numericas and codigo in codepoint2name:
            saida.append(f"&{codepoint2name[codigo]};")
        else:
            saida.append(f"&#{codigo};")
    return "".join(saida)


def hash_comunicacao(id_comunicacao: int) -> str:
    return hashlib.sha256(f"fixture-{id_comunicacao}".encode()).hexdigest()[:32]


def texto_ementa(e: dados.Ementa) -> str:
    _, mascara = numero_cnj(e.sequencial)
    corpo = "<br>".join(entidades(p, numericas=e.entidades_numericas) for p in e.corpo)
    if e.escape_duplo:
        corpo = corpo.replace("&", "&amp;")
    cabecalho = [
        ("Processo", f"{mascara}({e.classe})"),
        (e.rotulo_relator, e.relator),
        ("Órgão Julgador", e.orgao),
    ]
    if e.data_julgamento:
        cabecalho.append((e.rotulo_data, e.data_julgamento))
    if e.formato == "sem_tabela":
        linhas = "".join(
            f"<p><strong>{entidades(r)}:</strong>&nbsp;{entidades(v)}</p>" for r, v in cabecalho
        )
        return f"{linhas}<p><strong>Ementa:</strong></p><p>{corpo}</p>"
    linhas = "".join(
        f'<tr><td style="width:20%"><strong>{entidades(r)}:</strong>&nbsp;</td>'
        f"<td>{entidades(v)}</td></tr>"
        for r, v in cabecalho
    )
    return (
        '<table border="0" style="width:100%"><tbody>'
        f'{linhas}<tr><td colspan="2"><strong>Ementa:</strong><br>{corpo}</td></tr>'
        "</tbody></table>"
    )


def _destinatarios(id_comunicacao: int, pessoas: tuple[dados.Pessoa, ...]) -> list[dict[str, Any]]:
    return [{"nome": p.nome, "polo": p.polo, "comunicacao_id": id_comunicacao} for p in pessoas]


def _advogados(id_comunicacao: int, advogados: tuple[dados.Advogado, ...]) -> list[dict[str, Any]]:
    saida = []
    for advogado in advogados:
        id_advogado = int(advogado.oab)
        saida.append(
            {
                "id": id_comunicacao * 10 + len(saida),
                "comunicacao_id": id_comunicacao,
                "advogado_id": id_advogado,
                "created_at": f"2026-10-14T18:00:00{FUSO}",
                "updated_at": f"2026-10-14T18:00:00{FUSO}",
                "advogado": {
                    "id": id_advogado,
                    "nome": advogado.nome,
                    "numero_oab": advogado.oab,
                    "uf_oab": "PR",
                },
            }
        )
    return saida


def _item(
    *,
    id_comunicacao: int,
    data: str,
    sequencial: int,
    tipo_documento: str,
    tipo_comunicacao: str,
    orgao: str,
    classe: str,
    codigo_classe: int,
    texto: str,
    destinatarios: tuple[dados.Pessoa, ...],
    advogados: tuple[dados.Advogado, ...],
    cancelada: bool,
    nome_classe: str | None = None,
    sem_link: bool = False,
) -> dict[str, Any]:
    # Formato dos cadernos recentes (F1-01): sem numeroprocessocommascara, meiocompleto e
    # idOrgao; link pode ser nulo.
    digitos, _ = numero_cnj(sequencial)
    ano, mes, dia = data.split("-")
    return {
        "id": id_comunicacao,
        "data_disponibilizacao": data,
        "siglaTribunal": dados.TRIBUNAL,
        "tipoComunicacao": tipo_comunicacao,
        "nomeOrgao": orgao,
        "texto": texto,
        "numero_processo": digitos,
        "meio": "D",
        "link": None
        if sem_link
        else f"https://tribunal.exemplo.invalid/consulta/documento/{id_comunicacao}",
        "tipoDocumento": tipo_documento,
        "nomeClasse": nome_classe or classe,
        "codigoClasse": str(codigo_classe),
        "numeroComunicacao": id_comunicacao % 100000,
        "ativo": not cancelada,
        "hash": hash_comunicacao(id_comunicacao),
        # "C" nunca foi observado (F1-01): o cancelamento vem de ativo e data_cancelamento.
        "status": "P",
        "motivo_cancelamento": "Cancelamento solicitado pelo órgão" if cancelada else None,
        "data_cancelamento": f"2026-10-16T09:30:00{FUSO}" if cancelada else None,
        "datadisponibilizacao": f"{dia}/{mes}/{ano}",
        "dataenvio": f"{int(dia) - 1:02d}/{mes}/{ano}",
        "destinatarios": _destinatarios(id_comunicacao, destinatarios),
        "destinatarioadvogados": _advogados(id_comunicacao, advogados),
    }


def item_ementa(
    e: dados.Ementa, data: str = dados.DATA, *, cancelada: bool | None = None
) -> dict[str, Any]:
    return _item(
        id_comunicacao=e.id,
        data=data,
        sequencial=e.sequencial,
        tipo_documento="Ementa de Acórdão",
        tipo_comunicacao="Intimação",
        orgao=e.orgao,
        classe=e.classe,
        codigo_classe=e.codigo_classe,
        texto=texto_ementa(e),
        destinatarios=e.destinatarios,
        advogados=e.advogados,
        cancelada=e.cancelada if cancelada is None else cancelada,
        nome_classe=e.nome_classe_fonte,
        sem_link=e.sem_link,
    )


def item_outra(o: dados.Outra, data: str = dados.DATA) -> dict[str, Any]:
    return _item(
        id_comunicacao=o.id,
        data=data,
        sequencial=o.sequencial,
        tipo_documento=o.tipo_documento,
        tipo_comunicacao=o.tipo_comunicacao,
        orgao=o.orgao,
        classe=o.classe,
        codigo_classe=o.codigo_classe,
        texto=entidades(o.texto),
        destinatarios=o.destinatarios,
        advogados=o.advogados,
        cancelada=False,
    )


def itens_caderno(data: str, versao: int) -> list[dict[str, Any]]:
    if data == dados.DATA_SEM_EMENTAS:
        return [item_outra(o, data) for o in dados.OUTRAS]
    ementas = [
        item_ementa(
            e, data, cancelada=True if versao > 1 and e.id == dados.CANCELADA_NO_V2 else None
        )
        for e in dados.EMENTAS
        if not (versao > 1 and e.id == dados.AUSENTE_NO_V2)
    ]
    outras = [item_outra(o, data) for o in dados.OUTRAS]
    # Intercala as outras comunicações entre as ementas, como num caderno real.
    itens: list[dict[str, Any]] = []
    for i, ementa in enumerate(ementas):
        itens.append(ementa)
        if i % 3 == 1 and outras:
            itens.append(outras.pop(0))
    return itens + outras


def zip_caderno(data: str, versao: int) -> bytes:
    itens = itens_caderno(data, versao)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, inicio in enumerate(range(0, len(itens), ITENS_POR_ARQUIVO), start=1):
            pagina = itens[inicio : inicio + ITENS_POR_ARQUIVO]
            info = zipfile.ZipInfo(f"{dados.TRIBUNAL}-D-{data}_{n}.json", (2026, 10, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            # ensure_ascii: no caderno real, tipoDocumento vem como "Ementa de Acórdão".
            zf.writestr(
                info, json.dumps({"count": len(pagina), "items": pagina}, ensure_ascii=True)
            )
    return buffer.getvalue()


def metadados(
    data: str,
    versao: int,
    conteudo: bytes,
    *,
    status: str = "Processado",
    hash_correto: bool = True,
) -> dict[str, Any]:
    sha = hashlib.sha256(conteudo).hexdigest()
    return {
        "tribunal": dados.TRIBUNAL,
        "sigla_tribunal": dados.TRIBUNAL,
        "data": data,
        "meio": "D",
        "versao": versao,
        "status": status,
        "hash": sha if hash_correto else "0" * 64,
        "total_comunicacoes": len(itens_caderno(data, versao)),
        "numero_paginas": -(-len(itens_caderno(data, versao)) // ITENS_POR_ARQUIVO),
        "url": URL_ZIP.format(tribunal=dados.TRIBUNAL, data=data, versao=versao),
    }


def resposta_comunicacao(itens: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "success", "message": "Sucesso", "count": len(itens), "items": itens}


def arquivos() -> dict[str, bytes]:
    """Todos os arquivos da pasta de fixtures, por nome."""

    def js(objeto: Any) -> bytes:
        return (json.dumps(objeto, ensure_ascii=False, indent=2) + "\n").encode()

    saida: dict[str, bytes] = {}
    for data, versao in ((dados.DATA, 1), (dados.DATA, 2), (dados.DATA_SEM_EMENTAS, 1)):
        conteudo = zip_caderno(data, versao)
        saida[f"caderno-{data}-v{versao}.zip"] = conteudo
        saida[f"metadados-{data}-v{versao}.json"] = js(metadados(data, versao, conteudo))
    v1 = saida[f"caderno-{dados.DATA}-v1.zip"]
    saida[f"metadados-{dados.DATA}-v1-hash-incorreto.json"] = js(
        metadados(dados.DATA, 1, v1, hash_correto=False)
    )
    saida[f"metadados-{dados.DATA}-nao-processado.json"] = js(
        metadados(dados.DATA, 1, v1, status="Em processamento")
    )
    ausente = next(e for e in dados.EMENTAS if e.id == dados.AUSENTE_NO_V2)
    ativa = next(e for e in dados.EMENTAS if e.id == dados.EMENTAS[0].id)
    saida[f"comunicacao-{ausente.id}-cancelada.json"] = js(
        resposta_comunicacao([item_ementa(ausente, cancelada=True)])
    )
    saida[f"comunicacao-{ativa.id}-ativa.json"] = js(resposta_comunicacao([item_ementa(ativa)]))
    saida["comunicacao-nao-encontrada.json"] = js(resposta_comunicacao([]))
    saida["erro-429.json"] = js({"message": "Too Many Requests"})
    return saida


def gravar(pasta: Path = PASTA) -> list[str]:
    nomes = []
    for nome, conteudo in sorted(arquivos().items()):
        (pasta / nome).write_bytes(conteudo)
        nomes.append(nome)
    return nomes
