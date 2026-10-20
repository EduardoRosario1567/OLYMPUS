import React from 'react';

export default function App() {
  return (
    <div className="font-sans text-gray-900 bg-amber-50 min-h-screen flex flex-col">
      {/* Header */}
      <header className="sticky top-0 bg-amber-100 shadow-md">
        <nav className="max-w-7xl mx-auto flex justify-between items-center px-4 py-2">
          <a href="#hero" className="text-lg font-medium hover:underline">
            Rosales Café
          </a>
          <div className="flex gap-4">
            <a href="#concept" className="text-sm hover:underline">
              Conheça o conceito
            </a>
            <a href="#experience" className="text-sm hover:underline">
              Nossa proposta
            </a>
            <a href="#footer" className="text-sm hover:underline">
              Um convite a descobrir o café com atenção aos detalhes
            </a>
          </div>
        </nav>
      </header>

      {/* Hero */}
      <section
        id="hero"
        className="flex-1 flex flex-col items-center justify-center text-center px-4 py-16 bg-amber-100"
      >
        <h1 className="text-4xl md:text-6xl font-bold text-amber-900 mb-4">
          Rosales Café
        </h1>
        <p className="text-lg md:text-xl text-amber-800 mb-6">
          Café brasileiro com inspiração no estilo colombiano
        </p>
        <a
          href="#concept"
          className="inline-block px-6 py-2 bg-amber-700 text-white rounded hover:bg-amber-800 transition"
        >
          Uma pausa para apreciar o café
        </a>
      </section>

      {/* Concept */}
      <section id="concept" className="py-16 bg-amber-50">
        <div className="max-w-2xl mx-auto text-center px-4">
          <h2 className="text-3xl font-semibold text-amber-900 mb-4">
            Conheça o conceito
          </h2>
          <p className="text-lg text-amber-800 mb-4">Nossa proposta</p>
          <p className="text-base text-amber-700 mb-8">
            Um convite a descobrir o café com atenção aos detalhes
          </p>
          <div className="coffee-cup"></div>
        </div>
      </section>

      {/* Experience */}
      <section id="experience" className="py-16 bg-amber-100">
        <div className="max-w-2xl mx-auto text-center px-4">
          <h2 className="text-3xl font-semibold text-amber-900 mb-4">
            Nossa proposta
          </h2>
          <p className="text-base text-amber-700">
            Um convite a descobrir o café com atenção aos detalhes
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer id="footer" className="bg-amber-200 py-4">
        <div className="text-center text-sm text-amber-900">
          Rosales Café
        </div>
      </footer>
    </div>
  );
}
