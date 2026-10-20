# Validação da versão 0.1.0

Verificações executadas em 20/10/2026, no Windows 11, com Python 3.13.2.

## Suíte automatizada

- 21 testes descobertos.
- 20 aprovados.
- 1 pulado: criação de symlink indisponível para esta conta do Windows.
- Os dois testes reais de junções do Windows foram aprovados, incluindo rejeição de uma raiz que atravessava uma junção.

## Integração nativa

Uma pasta fictícia node_modules foi criada dentro do diretório de trabalho deste projeto. O scanner a identificou; a validação conferiu o alvo e a rotina nativa a enviou à Lixeira.

A presença dessa mesma pasta na Lixeira foi conferida pelo caminho original. Em seguida, ela foi restaurada e seu arquivo de teste foi encontrado novamente no local esperado.

Nenhuma dependência de projeto pessoal foi usada nesse teste.

## Executável

O executável foi gerado com PyInstaller 6.14.2. A inicialização empacotada da interface foi testada em modo oculto, verificando seleção vazia e botão de limpeza desabilitado; o processo terminou com código zero.

O inventário de terminal também foi executado sobre a pasta fictícia, com saída JSON e modo somente leitura.

## Limites desta validação

Não foram feitos testes em todas as edições do Windows, em instalações de terceiros, em discos de rede ou em árvores de projetos reais de grande porte. A suíte verifica estados e comportamento da interface; não inclui inspeção visual por captura de tela.

O workflow do GitHub foi preparado, mas ainda não foi executado em um repositório remoto.
