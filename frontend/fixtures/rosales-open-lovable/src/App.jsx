import React from "react";

export default function App() {
  return (
    <div className="container">
      {/* Header */}
      <header>
        <nav>
          <div className="logo">Rosales Café</div>
          <ul>
            <li><a href="#conceito">Conceito</a></li>
            <li><a href="#experiencia">Experiência</a></li>
            <li><a href="#proposta">Nossa proposta</a></li>
          </ul>
        </nav>
      </header>

      {/* Hero */}
      <section id="inicio">
        <div className="hero">
          <div className="hero-text">
            <h1>Rosales Café</h1>
            <p className="subtitle">Brasil na origem. Colômbia na inspiração.</p>
            <p className="hero-phrase">Café para quem aprecia o momento.</p>
            <a href="#conceito" className="cta-button">Conheça o conceito</a>
            <p>
              Rosales Café: a proposta de um café brasileiro com o estilo e a inspiração
              colombiana. Um convite a descobrir o café com atenção aos detalhes.
            </p>
          </div>
          <div className="hero-image">
            <div className="cup">
              <div className="handle"></div>
            </div>
          </div>
        </div>
      </section>

      {/* Conceito */}
      <section id="conceito">
        <div className="content">
          <h2>Conceito</h2>
          <h3>Conheça o conceito</h3>
          <p>O ritual faz parte da história.</p>
          <p>Uma identidade entre duas culturas do café.</p>
        </div>
      </section>

      {/* Experiência */}
      <section id="experiencia">
        <div className="content">
          <h2>Experiência</h2>
          <p>
            Esta é uma apresentação conceitual da marca, sem ofertas comerciais ou
            afirmações sobre produtos ainda não confirmadas.
          </p>
        </div>
      </section>

      {/* Nossa proposta */}
      <section id="proposta">
        <div className="content">
          <h2>Nossa proposta</h2>
          <p>
            Rosales Café: a proposta de um café brasileiro com o estilo e a inspiração
            colombiana. Um convite a descobrir o café com atenção aos detalhes.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer>
        <a href="#inicio">Voltar ao início</a>
        <span>© Rosales Café</span>
      </footer>
    </div>
  );
}