#!/usr/bin/env python3
"""Envia dossie existente ao adaptador OLYMPUS, somente por acao explicita."""
import argparse, datetime as dt, json, os, pathlib, sys
BASE=pathlib.Path(__file__).resolve().parent
OLYMPUS=pathlib.Path.home()/'Projetos-IA'/'OLYMPUS-TESTE'

def preparar(dossies):
    if not isinstance(dossies,list):
        raise ValueError('Dossies invalidos')
    itens=[]
    for d in dossies:
        if not isinstance(d,dict): continue
        itens.append({
            'produto':d.get('produto'),'codigo':d.get('codigo'),
            'evidencias':d.get('correlacoes_tendencias',[])[:5],
            'margem_contribuicao_estimada_pct':d.get('margem_contribuicao_estimada_pct'),
            'alertas':d.get('alertas',[]),'decisao_preliminar':d.get('decisao'),
            'volume_vendas':'NAO DETERMINADO'})
    return itens[:10]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--executar',action='store_true',
                        help='Chama explicitamente o modelo via OLYMPUS')
    parser.add_argument('--modelo',default='gemma4:31b-cloud')
    args=parser.parse_args()
    arquivo=BASE/'entrada_olympus.json'
    if not arquivo.exists():
        raise SystemExit('Execute inteligencia.py primeiro')
    dados=json.loads(arquivo.read_text(encoding='utf-8'))
    itens=preparar(dados['dossies'])
    if not args.executar:
        print('Dossies preparados:',len(itens))
        print('OLYMPUS NAO EXECUTADO: utilize --executar apenas quando o modelo retornar')
        return
    if not OLYMPUS.exists():
        raise SystemExit('OLYMPUS original nao encontrado')
    sys.path.insert(0,str(OLYMPUS))
    from olympus.routing.provider_fabric import ProviderConfig,OpenAICompatibleAdapter
    adaptador=OpenAICompatibleAdapter(ProviderConfig(
        provider_id='ollama',base_url='http://127.0.0.1:11434/v1',
        timeout_seconds=45))
    prompt=('Avalie os dados comerciais fornecidos. Nao invente demanda, vendas, '
            'fornecedores, faturamento nem lucro. Identifique lacunas de evidencia. '
            'Produza recomendacoes condicionais, citando exclusivamente as URLs '
            'presentes. DADOS: '+json.dumps(itens,ensure_ascii=False))
    resposta=adaptador.execute(model_id=args.modelo,prompt=prompt,max_tokens=700)
    auditoria={
        'executado_em_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'provider':'ollama','modelo':args.modelo,
        'sucesso':bool(resposta.success),
        'status':resposta.status,
        'erro':str(resposta.error or '')[:1000],
        'resposta':str(resposta.output or '')[:20000],
        'dossies_enviados':len(itens),
        'validacao_factual_realizada':False}
    caminho=BASE/'avaliacao_modelo.json'
    caminho.write_text(json.dumps(auditoria,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Status:',auditoria['status'],'| Sucesso:',auditoria['sucesso'])
    print('Auditoria:',caminho)
    if not resposta.success:
        raise SystemExit('Modelo indisponivel; nenhum resultado foi aprovado')

if __name__=='__main__':
    main()
