# Homologação

Use uma instância de homologação com banco e mídia isolados. As quantidades e valores abaixo são sintéticos. Prepare perfis reais de solicitação, compras, recebimento, aprovação, pagamento e leitura para verificar os controles do ERP.

## Compras, Almoxarifado e Suprimentos

1. Cadastre dois materiais de nomes semelhantes, com a mesma unidade, e duas obras. Registre um recebimento de 40 unidades para somente um dos materiais na primeira obra.
2. Abra uma compra avulsa de 100 unidades. Confirme o saldo 40 para a primeira obra e zero na segunda. Troque de material e alterne novamente a obra. O estoque exibido acompanha a seleção e a quantidade inicialmente a cotar é 100 quando o campo comercial fica em branco.
3. Fixe a quantidade a cotar em 60. Abra a edição da cotação, atualize o estoque e confirme os valores original 100 e comercial 60. Registre proposta, negocie, aprove e emita pedido de 60. Consulte o cronograma para conferir as transições.
4. Registre uma saída física de 40 no Almoxarifado. O fluxo usa o saldo físico e registra a movimentação. Tente nova saída acima do saldo e confirme o bloqueio.
5. Repita a consulta com uma falha de rede simulada. A interface exibe indisponibilidade. Envie a compra com dados válidos para conferir que a consulta é independente.
6. Consulte o Histórico de um processo com reserva legada. Confira o material, a quantidade reservada e o consumo original, inclusive para uma necessidade arquivada.

## Solicitações, divergências e aprovação

1. Emita pedido normal de 10 unidades por R$ 100,00. Confirme o compromisso de R$ 1.000,00 e a ausência de solicitação desse pedido antes do recebimento.
2. Registre 4 unidades, NF de R$ 400,00 e vencimento conhecido. Confirme a entrada no estoque, a solicitação de R$ 400,00 e sua presença junto de uma solicitação avulsa na central. A mesma nota no mesmo pedido deve produzir somente um recebimento e uma obrigação por parcela.
3. Registre segunda entrega de 3 unidades com NF coerente de R$ 320,00. Confira o esperado de R$ 300,00, diferença de R$ 20,00 e 6,67%. Verifique que a aprovação em lote deixa a divergência pendente. Aprove individualmente com ciência e justificativa e confira o histórico.
4. Use uma NF cuja soma de itens e frete difira do valor total. Confira a pendência no recebimento. Corrija seus campos fiscais, confira que as quantidades físicas permaneceram e verifique a solicitação resultante.
5. Abra a aprovação em dois navegadores ou abas. Em uma delas edite dados críticos ou solicite correção. Tente aprovar pela aba antiga e verifique a recusa do ciclo vencido. Reprove outro título e confira que ele fica fora dos pagamentos.
6. Teste as condições especiais de Grande Fornecedor e antecipação com fixtures específicas. Confira títulos, parcelas, aprovação, compensação e saldo. O histórico preserva o código financeiro e a origem.

## Pagamentos, malotes e indicadores

1. Em Pagamentos, selecione uma obra e o período. Inclua títulos aprovados de Compras e avulsos. Confira quantidade e total da seleção. Uma tentativa de misturar obras ou misturar uma obrigação administrativa com títulos de uma obra deve ser rejeitada.
2. Emita o malote. Abra o Excel e o ZIP, confira códigos, vencimentos, valores, notas corretas e comprovantes disponíveis. A emissão mantém os títulos aprovados com saldo.
3. Programe um título em data diferente do vencimento. Confirme a data original, registre o pagamento com comprovante e tente confirmar de novo. O histórico deve mostrar uma única efetivação. Estorne e verifique o retorno do saldo e a exclusão do valor de pagamentos efetivos.
4. Após um recebimento parcial, cancele o saldo a entregar. Confronte Compromissos, Planejamento, pagamentos e indicadores com o documento físico, verificando os valores contratado, recebido, aprovado, pago e cancelado sem somá-los como despesas independentes.

## PDF de cotação

1. Em Cadastros, preencha os dados institucionais e associe um logotipo não quadrado. Gere a solicitação geral e a versão de um fornecedor vinculado. Confira as informações da empresa, a proporção da imagem, o código, a obra, o fornecedor, as quantidades e as condições comerciais.
2. Em homologação, gere novamente com campos opcionais vazios e com logotipo indisponível. Confira a geração do arquivo e a presença dos dados restantes. Se houver storage híbrido, valide também um logo disponível somente por esse storage.
3. Use vários materiais e uma especificação maior que uma página. Confira os cabeçalhos repetidos, margens e itens das páginas seguintes. Abra o PDF com um perfil sem permissão de Compras e confirme a recusa.

## Diário de Obra e galeria — checklist pendente no navegador

1. Com um perfil autorizado de edição, abra um diário novo e preencha clima, efetivo, equipe e ocorrências. Anexe imagens válidas. Confirme que os novos arquivos estão no diretório privado `obras/diarios_privados/`, não na raiz pública de mídia.
2. Consulte diários antigos com fotos públicas ou armazenadas no Drive. Confira miniaturas, ampliação e download original, sem mover, apagar ou regravar os arquivos históricos.
3. Abra um diário sem fotos, um com 1 a 12 fotos e outro com mais de 12. Valide o agrupamento de fotos adicionais, o estado vazio, o indicador da posição e as imagens indisponíveis.
4. Verifique botões Anterior/Próxima, setas, Escape, retorno do foco e download do arquivo original. O original deve manter os bytes, não a miniatura.
5. No formulário, tente um arquivo inválido ou um formato não suportado. Confirme a mensagem e a preservação dos dados digitados. Arquivos precisam ser selecionados novamente após erro, por restrição do navegador.
6. Em homologação com armazenamento de teste, simule indisponibilidade do storage. Confira que não ficaram registros ou uploads parciais. Não simule falhas no ambiente produtivo.
7. Teste leitura, edição e ausência de autorização; verifique também que IDs de fotos de outros diários não podem ser usados no endereço do diário consultado.
8. Repita listagem, edição e galeria em 1366, 768 e 390 px, nos modos claro e escuro. Valide contraste, rolagem, foco e ausência de erros JavaScript.
9. Verifique que a raiz privada não está mapeada para `/media/`, `/static/` ou outras rotas públicas no servidor. Fotografias antigas mantêm o storage original e podem continuar diretamente acessíveis por seus endereços históricos. Não declare migração retroativa de privacidade concluída.

A retomada aprovou 13 testes de Diário em SQLite. A tentativa de navegador foi bloqueada pelo ambiente Linux; esta seção continua como checklist de homologação.
