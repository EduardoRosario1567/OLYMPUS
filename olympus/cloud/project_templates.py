"""Pinned, dependency-free Rosales Café MVP for controlled Cloud Beta onboarding.

A safe static template, not AI-generated content. No external network requests,
unsubstantiated facts, script execution, or business contact information.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

TEMPLATE_ID = "rosales_cafe_mvp"

INDEX_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Rosales Café — café brasileiro com inspiração no estilo colombiano. Conheça o conceito.">
  <meta name="color-scheme" content="light">
  <title>Rosales Café | Café brasileiro, inspiração colombiana</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <a class="skip" href="#conteudo">Pular para o conteúdo</a>
  <header class="site-header">
    <div class="shell header-inner">
      <a class="wordmark" href="#inicio" aria-label="Rosales Café — início"><span class="mark" aria-hidden="true">R</span><span>ROSALES <em>CAFÉ</em></span></a>
      <nav aria-label="Navegação principal"><a href="#conceito">Conceito</a><a href="#experiencia">Experiência</a><a href="#proposta">Nossa proposta</a></nav>
    </div>
  </header>
  <main id="conteudo">
    <section id="inicio" class="hero" aria-labelledby="titulo">
      <div class="shell hero-grid">
        <div class="hero-copy">
          <span class="eyebrow">Brasil na origem. Colômbia na inspiração.</span>
          <h1 id="titulo">Café para quem <span>aprecia o momento.</span></h1>
          <p>Rosales Café: a proposta de um café brasileiro com o estilo e a inspiração colombiana. Um convite a descobrir o café com atenção aos detalhes.</p>
          <div class="actions"><a class="primary" href="#conceito">Conheça o conceito <span aria-hidden="true">↗</span></a><a class="secondary" href="#proposta">Explore a proposta</a></div>
        </div>
        <div class="art" role="img" aria-label="Ilustração abstrata de uma xícara de café, em tons terrosos">
          <div class="disc"><div class="steam steam-a"></div><div class="steam steam-b"></div><div class="cup"><div class="coffee"></div></div><div class="saucer"></div></div>
          <div class="art-note"><strong>R O S A L E S</strong><span>café &amp; inspiração</span></div>
        </div>
      </div>
    </section>
    <section id="conceito" class="section cream" aria-labelledby="conceito-titulo">
      <div class="shell section-grid"><div><p class="eyebrow">01 · O conceito</p><h2 id="conceito-titulo">Uma identidade entre duas culturas do café.</h2></div>
      <div><p>O Rosales Café nasce aqui como uma proposta de marca: celebrar o café brasileiro com referências ao jeito colombiano de valorizar a experiência.</p><p>O conceito está em construção. As informações sobre produtos, origem dos lotes e canais de venda serão adicionadas apenas quando confirmadas.</p></div></div>
    </section>
    <section id="experiencia" class="section dark" aria-labelledby="experiencia-titulo">
      <div class="shell"><p class="eyebrow">02 · Experiência</p><h2 id="experiencia-titulo">O ritual faz parte da história.</h2><p class="intro">Da primeira pausa do dia às conversas que merecem mais tempo: uma marca pensada para acompanhar momentos simples.</p>
        <div class="pillars"><article><span class="number">01</span><h3>Pausa</h3><p>Um instante para sair do automático.</p></article><article><span class="number">02</span><h3>Encontro</h3><p>O café como convite à conversa.</p></article><article><span class="number">03</span><h3>Descoberta</h3><p>Curiosidade para conhecer novas referências.</p></article></div>
      </div>
    </section>
    <section id="proposta" class="section cream proposal" aria-labelledby="proposta-titulo"><div class="shell proposal-inner"><p class="eyebrow">03 · Nossa proposta</p><h2 id="proposta-titulo">Rosales Café.<br><em>Uma marca para descobrir.</em></h2><p>Esta é uma apresentação conceitual da marca, sem ofertas comerciais ou afirmações sobre produtos ainda não confirmadas.</p><a href="#inicio" class="secondary up">Voltar ao início ↑</a></div></section>
  </main>
  <footer class="footer"><div class="shell footer-inner"><strong>ROSALES CAFÉ</strong><span>Projeto conceitual · OLYMPUS Beta privada</span></div></footer>
</body>
</html>
"""

STYLE_CSS = """@charset "UTF-8";
:root{--ink:#231d19;--sand:#f7f1e6;--cream:#fcf9f3;--copper:#99562f;--muted:#63574e;--dark:#29211d}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:var(--cream);line-height:1.6}a{color:inherit}a:focus-visible{outline:3px solid #ba612a;outline-offset:4px}.shell{width:min(1120px,calc(100% - 40px));margin-inline:auto}.skip{position:absolute;left:16px;top:-80px;z-index:100;padding:10px;background:#fff}.skip:focus{top:16px}.site-header{background:#fbf7ef;border-bottom:1px solid #e4d9c8}.header-inner{display:flex;align-items:center;justify-content:space-between;gap:20px;min-height:90px}.wordmark{display:inline-flex;align-items:center;gap:12px;text-decoration:none;font-size:15px;font-weight:850;letter-spacing:.08em}.wordmark em{font-style:normal;color:var(--copper)}.mark{display:grid;place-items:center;width:42px;height:42px;border-radius:50%;background:var(--dark);color:#fff;font-family:Georgia,serif;font-size:27px}.site-header nav{display:flex;gap:clamp(12px,3vw,32px);font-size:13px;font-weight:650}.site-header nav a{text-decoration:none}.site-header nav a:hover,.secondary:hover{text-decoration:underline}.hero{background:linear-gradient(135deg,#fbf7ef 0%,#eae0d1 100%)}.hero-grid{display:grid;grid-template-columns:1.15fr .85fr;min-height:620px;gap:45px;align-items:center;padding-block:74px}.eyebrow{text-transform:uppercase;letter-spacing:.2em;font-size:11px;font-weight:850;color:var(--copper)}h1,h2,h3,p{margin-top:0}h1,h2{font-family:Georgia,"Times New Roman",serif;letter-spacing:-.045em;font-weight:400;line-height:1.08}h1{font-size:clamp(51px,6vw,91px);margin:22px 0 25px}h1 span{font-style:italic;color:var(--copper)}.hero-copy>p{max-width:500px;font-size:17px;color:#554c43}.actions{display:flex;flex-wrap:wrap;gap:20px;align-items:center;margin-top:32px}.primary{display:inline-flex;gap:22px;align-items:center;background:var(--ink);color:#fff;padding:15px 20px;text-decoration:none;font-weight:700;font-size:13px;border:2px solid var(--ink);border-radius:4px}.primary:hover{background:#523a29}.secondary{font-size:13px;font-weight:800;text-underline-offset:5px}.art{position:relative;min-height:410px;display:flex;align-items:center;justify-content:center;border:1px solid #d5c4ae;border-radius:180px 180px 14px 14px;background:radial-gradient(circle at 50% 38%,#e9ccac,#d0a77e 70%,#ba8b61);overflow:hidden}.disc{position:relative;width:270px;height:270px;border-radius:50%;background:#e8c6a3;display:grid;place-items:center;box-shadow:0 25px 60px #6c3b1e35}.cup{position:absolute;top:88px;left:75px;width:120px;height:103px;background:#fff7e8;border:9px solid #eee4d1;border-radius:10px 10px 62px 62px;z-index:2;box-shadow:3px 9px 0 #9f6e4a}.cup:after{content:"";position:absolute;left:100px;top:12px;border:13px solid #fff7e8;width:37px;height:44px;border-radius:50%}.coffee{position:absolute;top:-7px;left:0;width:100%;height:23px;background:#5d331d;border-radius:50%}.saucer{position:absolute;left:56px;top:183px;width:163px;height:26px;border-radius:50%;background:#f8e7ce;z-index:1}.steam{position:absolute;top:34px;width:9px;height:35px;border-left:4px solid #7d523b;border-radius:50%;opacity:.7}.steam-a{left:116px}.steam-b{left:144px;top:22px}.art-note{position:absolute;bottom:20px;display:flex;flex-direction:column;align-items:center;gap:3px;color:#422a20;font-size:10px;letter-spacing:.15em}.art-note span{font-style:italic;letter-spacing:.04em}.section{padding-block:105px}.cream{background:var(--cream)}.section-grid{display:grid;grid-template-columns:1fr 1fr;gap:90px;align-items:start}.section h2{font-size:clamp(38px,4.2vw,63px);max-width:650px;margin:18px 0 0}.section-grid div:last-child{padding-top:53px}.section-grid div:last-child p{font-size:17px;line-height:1.8;color:var(--muted)}.dark{background:var(--dark);color:var(--cream)}.dark .eyebrow{color:#dcb58e}.dark .intro{color:#e0d2c2;max-width:630px;font-size:18px;margin:22px 0 55px}.pillars{display:grid;grid-template-columns:repeat(3,1fr);gap:35px}.pillars article{border-top:1px solid #917a67;padding-top:25px}.pillars .number{color:#dcb58e;font-size:12px;letter-spacing:.2em}.pillars h3{font-family:Georgia,serif;font-weight:400;font-size:30px;margin:13px 0}.pillars p{color:#e1d2c5}.proposal{text-align:center}.proposal-inner{max-width:780px}.proposal h2{max-width:none;margin:20px 0 25px}.proposal h2 em{color:var(--copper)}.proposal p:not(.eyebrow){max-width:570px;margin:0 auto 25px;color:var(--muted)}.footer{background:#e9ddce;padding:28px 0}.footer-inner{display:flex;justify-content:space-between;gap:18px;font-size:12px;color:#4f4236}
@media(max-width:760px){.shell{width:min(100% - 34px,590px)}.header-inner{min-height:80px;flex-wrap:wrap;padding-block:15px;justify-content:center}.site-header nav{width:100%;justify-content:center;gap:19px;font-size:12px}.hero-grid{grid-template-columns:1fr;min-height:0;padding-block:60px;gap:43px}.hero-copy{max-width:570px}h1{font-size:clamp(47px,13vw,76px)}.art{max-width:500px;width:100%;margin-inline:auto;min-height:340px}.section{padding-block:70px}.section-grid{grid-template-columns:1fr;gap:18px}.section-grid div:last-child{padding-top:0}.pillars{grid-template-columns:1fr;gap:18px}.pillars article{padding-top:17px}.footer-inner{flex-direction:column;align-items:center;text-align:center}.actions{gap:19px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""

def write_rosales_mvp(project_root: Path) -> dict[str, str]:
    """Add the two known, immutable text assets to a freshly created project."""
    root = project_root.resolve(strict=True)
    if not root.is_dir() or any(root.iterdir()):
        raise ValueError("MVP template requires a new, empty project")
    files = {"index.html": INDEX_HTML, "style.css": STYLE_CSS}
    for name, content in files.items():
        target = root / name
        with target.open("x", encoding="utf-8") as stream:
            stream.write(content)
    return {name: sha256(value.encode("utf-8")).hexdigest() for name, value in files.items()}
