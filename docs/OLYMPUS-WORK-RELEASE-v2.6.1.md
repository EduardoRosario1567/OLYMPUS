# OLYMPUS Work v2.6.1 — Hotfix de homologação macOS

## Resultado

O inicializador deixa de comparar os serviços ativos com a versão antiga 2.4.0
e passa a ler a versão diretamente do manifesto público do pacote. Backend e
frontend somente são considerados atuais quando confirmam exatamente essa
versão.

## Pré-voo

Antes de criar ambientes ou instalar dependências, o inicializador confirma a
presença de curl, Python, Node.js e npm, além das versões mínimas Python 3.9 e
Node.js 18. Falhas recebem uma orientação curta em português.

## Limite honesto

Esta é uma versão de homologação local. A primeira abertura ainda baixa
dependências e requer Python e Node previamente instalados. O aplicativo
autônomo compilado, assinado e notarizado permanece uma etapa posterior.
