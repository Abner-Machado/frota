# frota - contrato de construção

Objetivo: unificar quatro ferramentas já publicadas num único pacote Python com um comando.

| Ferramenta antiga | Virou | Origem do código |
|---|---|---|
| `context-lint` | `frota lint` | `C:\Users\abner\AppData\Local\Temp\opencode\frota-review\context-lint\context_lint.py` |
| `prompt-diff` | `frota diff` | `C:\Users\abner\AppData\Local\Temp\opencode\frota-review\prompt-diff\prompt_diff.py` (v1.1.0) |
| `skill-audit` | `frota audit` | `C:\Users\abner\AppData\Local\Temp\opencode\frota-review\skill-audit\skill_audit.py` (v1.1.0) |
| `agent-log` | `frota log` | `C:\Users\abner\OpenBot\Agents\agent-dc17f158-cf2e-46f6-a619-41bbf06d027f\agent-log\agent_log.js` |

Os quatro originais já contêm correções que não estão no GitHub antigo. **Portar destes
arquivos, não das versões publicadas.**

## Regras do pacote

- Python 3.8+, **zero dependências** (só biblioteca padrão).
- Código e comentários em inglês; nada de atribuição a IA.
- Token estimado vem sempre de `frota/_tokens.py` (`estimate_tokens`), não duplicar a fórmula.
- Saída legível por padrão, `--json` para máquina, `--no-color` onde há cor.
- Nunca misturar saída de diagnóstico com `stdout`: erro vai para `stderr`.

## Arquivos e dono — ninguém edita arquivo de outro

| Arquivo | Dono |
|---|---|
| `frota/lint_context.py`, `frota/audit_skill.py` | [BACKEND] Jorge Paulo Lemann |
| `frota/diff_prompt.py`, `frota/log.py`, `tests/` | [FULLSTACK] Marcel Telles |
| `frota/cli.py`, `frota/_tokens.py`, `frota/__init__.py`, `pyproject.toml`, `CONTRACT.md`, `README.md`, `LICENSE` | orquestrador (congelados) |

`frota/cli.py` já roteia os quatro subcomandos e chama `run(argv)`. Não precisa, e não
pode, ser alterado.

## Interface fixa

```
frota lint <file.md> [--max-tokens N] [--json] [--no-color]
frota diff <old.md> <new.md> [--context N] [--json] [--no-color]
frota audit <file.md> [--json]
frota log <file.jsonl> [--json]
```

Cada módulo expõe `run(argv: list[str]) -> int` e devolve o código de saída.

| Comando | 0 | 1 | 2 |
|---|---|---|---|
| `lint` | dentro do orçamento ou sem limite | estourou o orçamento | uso/arquivo |
| `diff` | leu os dois arquivos | — | uso/arquivo |
| `audit` | limpo | achou risco | uso/arquivo |
| `log` | resumo impresso | — | uso/arquivo |

## Uso do `frota log`

`agent_log.js` era biblioteca. Em Python vira `frota.log.create_logger(...)` com a mesma
API (`debug/info/warn/error/step/summary/close`), gravando JSONL, e o subcomando
`frota log <arquivo.jsonl>` lê esse JSONL e imprime o resumo: total de passos, erros,
tokens, duração em ms e janela de tempo.

## O que não fazer

- Não rodar `git add`, `git commit` ou `git push`. Publicação é do Abner.
- Não criar arquivo fora de `C:\Users\abner\OpenBot\Shared\frota`.
- Não reescrever `cli.py` para "melhorar" a interface.
- Não adicionar dependência, plugin ou framework de teste externo.

## Pronto quando

1. `python -m frota lint|diff|audit|log ...` funciona nos arquivos de exemplo.
2. `python -m frota --help` e `frota <cmd> --help` mostram ajuda sem erro.
3. Arquivo inexistente devolve 2 e mensagem em `stderr`, sem traceback.
4. `--json` devolve JSON válido em todos os quatro.
5. Saída antiga continua compatível: nenhum campo do JSON original removido sem aviso.
