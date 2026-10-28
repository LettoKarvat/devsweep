# DevSweep

Aplicativo desktop para Windows que encontra dependências de desenvolvimento ocupando espaço e permite revisar as pastas antes de enviá-las à Lixeira.

**Node.js + Python · interface em português · funcionamento local · sem bibliotecas externas em execução**

## O que encontra

| Tipo | Detecção |
| --- | --- |
| Node.js | Diretórios chamados exatamente `node_modules` |
| Ambientes virtuais Python | Diretórios com o arquivo `pyvenv.cfg`, independentemente do nome |
| Caches Python | `__pycache__`, `.pytest_cache`, `.mypy_cache` e `.ruff_cache` |

Não confunde uma pasta chamada `env` ou `venv` com um ambiente se o marcador estiver ausente. Não propõe a remoção isolada de `site-packages`.

## Executar

No Windows 10 ou 11, baixe **DevSweep.exe** na [página de versões](https://github.com/LettoKarvat/devsweep/releases/latest) e abra o arquivo.

Para executar o código-fonte, é necessário Python 3.11 ou superior com Tkinter. Na pasta do projeto:

```powershell
py -3 -m devsweep
```

Também é possível abrir `iniciar.cmd`. Nenhuma instalação de pacote é necessária.

1. Escolha uma pasta ou **Discos locais**, que inclui os discos fixos acessíveis.
2. Selecione os tipos e os filtros de idade e tamanho; use zero para exibir todas as candidatas.
3. Clique em **Escanear**. A busca é somente leitura e pode ser interrompida.
4. Revise as linhas; clique duas vezes para ver detalhes.
5. Marque as pastas desejadas e confirme **Enviar selecionadas à Lixeira**.
6. Restaure pelo Windows se necessário. Esvaziar a Lixeira, por decisão do usuário, libera o espaço.

## Exportar inventário

Após a busca, clique em **Exportar relatório** e escolha CSV ou JSON na janela de salvamento.
O relatório contém todas as pastas exibidas, inclusive as bloqueadas; as marcações para limpeza não limitam a exportação.

O JSON inclui a versão do aplicativo e do formato, a data de geração em UTC, as raízes das candidatas, os tamanhos lógicos,
as restrições de cada pasta e os contadores da busca. Uma busca interrompida fica identificada como parcial (`cancelled`).
As raízes aparecem somente quando há candidatas exibidas naquele alcance.
O mesmo formato está disponível no terminal com `--json`. Os relatórios são informativos e não autorizam limpeza.

## Como a idade é estimada

O aplicativo usa a alteração mais recente encontrada nas dependências e nos arquivos do projeto. Procura um manifesto próximo, como `package.json` ou `pyproject.toml`, e inspeciona os arquivos desse projeto, excluindo dependências, caches e `.git`.

**Data de modificação não comprova quando um programa foi executado.** Um projeto ativo também pode ficar muito tempo sem alterações. Por isso o DevSweep não chama essas pastas de lixo e não as seleciona automaticamente.

A leitura dos arquivos de um projeto tem limite de 20.000 entradas. Quando a medição ou essa análise fica incompleta, a pasta permanece somente no inventário.

## Comportamento da limpeza

- A busca não apaga, move ou modifica arquivos.
- Antes de cada envio, o caminho absoluto é resolvido e conferido dentro da raiz escaneada.
- Identidade do diretório e metadados de seu conteúdo são comparados com o inventário. Mudanças exigem nova busca.
- Links, junções e outros pontos de redirecionamento não são percorridos. Candidatas que os contenham ficam bloqueadas para limpeza nesta versão.
- Diretórios do Windows, Program Files, ProgramData, a instalação Python usada pelo próprio aplicativo e caminhos globais conhecidos são ignorados.
- A própria raiz selecionada não pode ser removida.
- O envio usa a API nativa IFileOperation e a opção RECYCLEONDELETE no Windows. Não há rotina alternativa de exclusão permanente.
- Falhas de acesso ou cancelamentos são apresentados na interface. Nenhuma elevação administrativa é solicitada pelo aplicativo.
- O aplicativo não esvazia a Lixeira.

O tamanho é a soma dos tamanhos lógicos dos arquivos; não mede blocos efetivamente alocados. Compressão, arquivos esparsos, links físicos e conteúdo já compartilhado podem fazer o ganho real ser menor.

Ambientes virtuais podem conter arquivos que uma pessoa salvou manualmente dentro deles. Confira o conteúdo antes de selecioná-los. Dependências podem ser reconstruídas com os manifestos do projeto, mas versões indisponíveis e dependências privadas podem exigir procedimentos adicionais.

## Terminal: somente inventário

```powershell
py -3 -m devsweep --scan "C:\Projetos" --days 60 --min-mb 10
py -3 -m devsweep --scan "C:\Projetos" --days 0 --min-mb 0 --json
py -3 -m devsweep --scan "C:\Projetos" --csv inventario.csv
```

O terminal não oferece comando de remoção. Os relatórios não podem ser importados para autorizar limpeza.

## Testes

```powershell
py -3 -m unittest discover -s tests -v
```

A suíte cria projetos fictícios em `.test-work`; não escaneia os projetos pessoais do usuário. Ela verifica contagem sem duplicação, identificação de ambientes, alterações posteriores ao inventário, escopo, cancelamento e estados da interface. Testes de symlink podem ser pulados quando o Windows não permite criá-los; as junções têm testes próprios.

## Gerar o executável

O empacotamento usa PyInstaller como dependência de desenvolvimento:

```powershell
py -3 -m venv .venv-build
.\.venv-build\Scripts\python -m pip install pyinstaller
.\.venv-build\Scripts\python -m PyInstaller --onefile --windowed --name DevSweep launcher.pyw
```

## Estrutura

- `devsweep/core.py`: descoberta, inventário, validação e exportação.
- `devsweep/app.py`: interface, seleção e tarefas em segundo plano.
- `devsweep/windows.py`: discos locais e integração com a Lixeira.
- `devsweep/__main__.py`: entrada de terminal somente leitura.
- `tests/`: testes com diretórios fictícios.
- `docs/`: decisões de projeto, notas da versão e validação.

## Desenvolvimento

A ideia e a definição inicial do problema são de [LettoKarvat](https://github.com/LettoKarvat). A implementação e as atualizações foram produzidas com assistência de IA.
