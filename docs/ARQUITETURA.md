# Arquitetura e decisões

## Problema

Projetos antigos acumulam dependências de Node.js, ambientes Python e caches. Encontrar essas pastas manualmente exige visitar vários diretórios e medir seu conteúdo.

O DevSweep entrega descoberta, medição, classificação e uma seleção revisada para envio à Lixeira.

## Fluxo

1. O usuário define raízes e tipos de dependência.
2. O scanner percorre os diretórios iterativamente, sem seguir redirecionamentos.
3. Ao encontrar uma dependência, mede seu conteúdo e não procura candidatas dentro dela.
4. O scanner consulta a atividade dos arquivos do projeto e guarda um retrato de metadados.
5. A interface filtra o inventário por tamanho e idade, inicialmente sem seleção.
6. Após revisão, a limpeza revalida cada pasta e solicita a operação ao Windows.

## Separação

A interface Tkinter roda na thread principal. Busca e limpeza usam workers e uma fila; os workers não acessam widgets. O cancelamento da busca utiliza threading.Event.

O núcleo pode ser chamado pelo terminal sem inicializar Tkinter. A rotina de reciclagem é injetável nos testes, para testar recusas sem remover dados.

## Complexidade e limites

O percurso é proporcional ao número de entradas acessíveis. A medição de uma dependência tem custo proporcional ao seu conteúdo. A inspeção dos arquivos de cada projeto é compartilhada entre candidatas desse mesmo projeto e limitada a 20.000 entradas.

O tamanho é lógico. O aplicativo não calcula alocação de disco nem deduplica links físicos entre arquivos. Não identifica de forma confiável todos os processos que usam dependências; arquivos em uso podem ser recusados pelo Windows.

Os retratos comparam caminhos, identidade e metadados. Não são hashes completos do conteúdo dos arquivos. Mudanças concorrentes entre a última verificação e a operação do sistema ainda são uma limitação; não execute sobre árvores que outros processos estejam modificando.

## Reciclagem

No Windows, um worker inicializa COM em modo STA e usa IFileOperation com RECYCLEONDELETE, registro de desfazer e interrupção em erro. A implementação não chama shutil.rmtree nem possui fallback para exclusão permanente.

Referências:

- [IFileOperation](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifileoperation)
- [SetOperationFlags e RECYCLEONDELETE](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags)

## Melhorias possíveis

- Tratar dependências pnpm com links por meio de uma política específica e testes adicionais.
- Incluir estimativa de espaço alocado, além do tamanho lógico.
- Acrescentar exclusões de pastas definidas pelo usuário.
- Assinar digitalmente as versões distribuídas.
- Estudar suporte de limpeza em outros sistemas operacionais.
