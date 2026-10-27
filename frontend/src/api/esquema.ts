// Gerado por scripts/api.mjs a partir de openapi.json. Não edite à mão.
// Para regenerar: pnpm api:gerar

export interface paths {
    "/api/v1/saude": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Saude */
        get: operations["saude_api_v1_saude_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/busca": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Buscar
         * @description Busca híbrida, ou por número de processo quando a consulta é um número (F4-02).
         */
        get: operations["buscar_api_v1_busca_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/acordaos/{acordao_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Detalhe
         * @description Detalhe; 410 para cancelado ou removido, 404 para inexistente ou em quarentena.
         */
        get: operations["detalhe_api_v1_acordaos__acordao_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/processos/{numero}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Processo
         * @description Acórdãos de um processo, com ou sem máscara (prefixo a partir de NNNNNNN-DD).
         */
        get: operations["processo_api_v1_processos__numero__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/filtros": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Filtros */
        get: operations["filtros_api_v1_filtros_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/relatores": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Relatores */
        get: operations["relatores_api_v1_relatores_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/remocao": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Remocao
         * @description Pedido de remoção (canal da seção 6.5).
         */
        post: operations["remocao_api_v1_remocao_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AcordaosDoProcesso */
        AcordaosDoProcesso: {
            /** Numero Processo */
            numero_processo: string;
            /**
             * Acordaos
             * @description Do mais recente ao mais antigo
             */
            acordaos: components["schemas"]["ResultadoBusca"][];
        };
        /** Classe */
        Classe: {
            /**
             * Codigo
             * @description Código da classe na TPU do CNJ
             */
            codigo: number | null;
            /** Nome */
            nome: string | null;
        };
        /** DetalheAcordao */
        DetalheAcordao: {
            /** Id */
            id: number;
            /**
             * Fonte
             * @enum {string}
             */
            fonte: "djen" | "tjdft";
            /**
             * Tribunal
             * @example TJPR
             * @example TJDFT
             */
            tribunal: string;
            /**
             * Numero Processo
             * @description Número CNJ com máscara
             */
            numero_processo: string;
            /** Orgao Julgador */
            orgao_julgador: string | null;
            classe: components["schemas"]["Classe"];
            /** Relator */
            relator: string | null;
            /**
             * Relator Designado
             * @description TJDFT: relator para o acórdão (a citação usa 'Rel. p/ acórdão')
             */
            relator_designado: string | null;
            /** Turma Recursal */
            turma_recursal: boolean | null;
            /** Data Julgamento */
            data_julgamento: string | null;
            /**
             * Data Publicacao
             * @description TJDFT; nula no DJEN (não é calculada)
             */
            data_publicacao: string | null;
            /**
             * Data Disponibilizacao
             * @description DJEN
             */
            data_disponibilizacao: string | null;
            /**
             * Link Oficial
             * @description DJEN: certidão do CNJ; TJDFT: página do acórdão
             */
            link_oficial: string;
            /**
             * Link Tribunal
             * @description DJEN: documento no sistema do tribunal
             */
            link_tribunal: string | null;
            /**
             * Citacao
             * @description Copiar exatamente como veio (regra da seção 9)
             */
            citacao: string;
            /**
             * Aviso
             * @default Texto reproduzido da fonte oficial. Consulte o documento original.
             */
            aviso: string;
            /** Ementa */
            ementa: string;
            /**
             * Decisao
             * @description TJDFT: dispositivo
             */
            decisao: string | null;
            /** Possui Inteiro Teor */
            possui_inteiro_teor: boolean | null;
        };
        /** Erro */
        Erro: {
            /**
             * Erro
             * @description Código do erro, estável (ex.: nao_encontrado)
             */
            erro: string;
            /** Mensagem */
            mensagem: string;
        };
        /** Filtros */
        Filtros: {
            /** Tribunais */
            tribunais: components["schemas"]["OpcaoFiltro"][];
            /** Orgaos */
            orgaos: components["schemas"]["OpcaoFiltro"][];
            /** Classes */
            classes: components["schemas"]["OpcaoFiltro"][];
        };
        /** FiltrosBusca */
        FiltrosBusca: {
            /** Tribunal */
            tribunal?: string | null;
            /** Orgao */
            orgao?: string | null;
            /** Classe */
            classe?: number | null;
            /**
             * Relator
             * @description relator_chave
             */
            relator?: string | null;
            /** Data Inicio */
            data_inicio?: string | null;
            /** Data Fim */
            data_fim?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * Indisponivel
         * @description Acórdão que existiu mas não pode ser exibido (HTTP 410).
         */
        Indisponivel: {
            /**
             * Erro
             * @enum {string}
             */
            erro: "cancelado" | "removido";
            /** Mensagem */
            mensagem: string;
            /**
             * Link Oficial
             * @description Fonte oficial, quando ainda faz sentido indicá-la
             */
            link_oficial?: string | null;
        };
        /** OpcaoFiltro */
        OpcaoFiltro: {
            /** Valor */
            valor: string;
            /** Rotulo */
            rotulo: string;
            /** Total */
            total: number;
        };
        /** PedidoRemocao */
        PedidoRemocao: {
            /**
             * Referencia
             * @description Número do processo ou link do resultado
             */
            referencia: string;
            /** Motivo */
            motivo: string;
            /**
             * Email
             * @description Usado só para responder; apagado após a resolução
             */
            email: string;
        };
        /** Relator */
        Relator: {
            /** Nome */
            nome: string;
            /**
             * Chave
             * @description Valor do filtro 'relator' na busca
             */
            chave: string;
        };
        /** RemocaoRecebida */
        RemocaoRecebida: {
            /** Protocolo */
            protocolo: number;
            /**
             * Status
             * @constant
             */
            status: "pendente";
            /** Mensagem */
            mensagem: string;
        };
        /** RespostaBusca */
        RespostaBusca: {
            /**
             * Consulta
             * @description Consulta normalizada
             */
            consulta: string;
            /**
             * Tipo
             * @description processo: a consulta era um número de processo (busca exata ou prefixo)
             * @enum {string}
             */
            tipo: "hibrida" | "processo";
            /**
             * Numero Processo
             * @description Número detectado na consulta (com máscara, ou os dígitos do prefixo)
             */
            numero_processo: string | null;
            filtros: components["schemas"]["FiltrosBusca"];
            /** Pagina */
            pagina: number;
            /**
             * Por Pagina
             * @default 20
             */
            por_pagina: number;
            /**
             * Total
             * @description Até 200; não há páginas além disso
             */
            total: number;
            /** Resultados */
            resultados: components["schemas"]["ResultadoBusca"][];
        };
        /** ResultadoBusca */
        ResultadoBusca: {
            /** Id */
            id: number;
            /**
             * Fonte
             * @enum {string}
             */
            fonte: "djen" | "tjdft";
            /**
             * Tribunal
             * @example TJPR
             * @example TJDFT
             */
            tribunal: string;
            /**
             * Numero Processo
             * @description Número CNJ com máscara
             */
            numero_processo: string;
            /** Orgao Julgador */
            orgao_julgador: string | null;
            classe: components["schemas"]["Classe"];
            /** Relator */
            relator: string | null;
            /**
             * Relator Designado
             * @description TJDFT: relator para o acórdão (a citação usa 'Rel. p/ acórdão')
             */
            relator_designado: string | null;
            /** Turma Recursal */
            turma_recursal: boolean | null;
            /** Data Julgamento */
            data_julgamento: string | null;
            /**
             * Data Publicacao
             * @description TJDFT; nula no DJEN (não é calculada)
             */
            data_publicacao: string | null;
            /**
             * Data Disponibilizacao
             * @description DJEN
             */
            data_disponibilizacao: string | null;
            /**
             * Link Oficial
             * @description DJEN: certidão do CNJ; TJDFT: página do acórdão
             */
            link_oficial: string;
            /**
             * Link Tribunal
             * @description DJEN: documento no sistema do tribunal
             */
            link_tribunal: string | null;
            /**
             * Citacao
             * @description Copiar exatamente como veio (regra da seção 9)
             */
            citacao: string;
            /**
             * Aviso
             * @default Texto reproduzido da fonte oficial. Consulte o documento original.
             */
            aviso: string;
            /**
             * Trecho
             * @description Trecho da ementa; o único HTML possível é <mark> em volta dos termos
             */
            trecho: string;
        };
        /** Saude */
        Saude: {
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "erro";
            /**
             * Banco
             * @enum {string}
             */
            banco: "ok" | "erro";
            /** Versao */
            versao: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    saude_api_v1_saude_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Saude"];
                };
            };
        };
    };
    buscar_api_v1_busca_get: {
        parameters: {
            query: {
                q: string;
                tribunal?: string | null;
                orgao?: string | null;
                /** @description Código da classe na TPU */
                classe?: number | null;
                /** @description relator_chave (ver /relatores) */
                relator?: string | null;
                data_inicio?: string | null;
                data_fim?: string | null;
                pagina?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RespostaBusca"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
        };
    };
    detalhe_api_v1_acordaos__acordao_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                acordao_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetalheAcordao"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
            /** @description Gone */
            410: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Indisponivel"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
        };
    };
    processo_api_v1_processos__numero__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                numero: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcordaosDoProcesso"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
        };
    };
    filtros_api_v1_filtros_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Filtros"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
        };
    };
    relatores_api_v1_relatores_get: {
        parameters: {
            query: {
                prefixo: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Relator"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
        };
    };
    remocao_api_v1_remocao_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PedidoRemocao"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RemocaoRecebida"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Erro"];
                };
            };
        };
    };
}
