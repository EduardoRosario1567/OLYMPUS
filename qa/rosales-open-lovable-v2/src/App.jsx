import React from "react";

export default function App() {
  return (
    <div className="font-sans text-gray-900 bg-amber-50 min-h-screen">
      {/* Header */}
      <header className="bg-amber-200 sticky top-0 z-10">
        <nav className="max-w-7xl mx-auto flex justify-between items-center p-4">
          <a href="#inicio" className="text-2xl font-bold text-amber-800">
            Rosales Café
          </a>
          <ul className="flex space-x-4">
            <li>
              <a href="#conceito" className="hover:text-amber-600 transition-colors">
                Conceito
              </a>
            </li>
            <li>
              <a href="#experiencia" className="hover:text-amber-600 transition-colors">
                Experiência
              </a>
            </li>
            <li>
              <a href="#proposta" className="hover:text-amber-600 transition-colors">
                Nossa proposta
              </a>
            </li>
          </ul>
        </nav>
      </header>

      <main className="space-y-16 py-8">
        {/* Hero / Início */}
        <section id="inicio" className="text-center px-4">
          <h1 className="text-4xl md:text-6xl font-extrabold text-amber-900 mb-4 animate-fade-in">
            Rosales Café
          </h1>
          <p className="text-lg md:text-xl text-amber-800 mb-6">
            Brasil na origem. Colômbia na inspiração.
          </p>
          <div className="cup mb-8"></div>
          <a
            href="#conceito"
            className="inline-block bg-amber-600 text-white px-6 py-3 rounded-full hover:bg-amber-700 transition-colors"
          >
            Conheça o conceito
          </a>
        </section>

        {/* Conceito */}
        <section id="conceito" className="bg-amber-100 py-12 px-4 md:px-16">
          <h2 className="text-3xl md:text-4xl font-semibold text-amber-900 mb-4 text-center">
            Conceito
          </h2>
          <p className="max-w-3xl mx-auto text-center text-amber-800">
            Esta é uma apresentação conceitual da marca, sem ofertas comerciais ou
            afirmações sobre produtos ainda não confirmadas.
          </p>
          <div className="text-center mt-6">
            <a href="#inicio" className="text-amber-600 hover:underline">
              Voltar ao início
            </a>
          </div>
        </section>

        {/* Experiência */}
        <section id="experiencia" className="py-12 px-4 md:px-16">
          <h2 className="text-3xl md:text-4xl font-semibold text-amber-900 mb-4 text-center">
            Experiência
          </h2>
          <p className="max-w-3xl mx-auto text-center text-amber-800 mb-4">
            Café para quem aprecia o momento.
          </p>
          <p className="max-w-3xl mx-auto text-center text-amber-800">
            O ritual faz parte da história.
          </p>
          <div className="text-center mt-6">
            <a href="#inicio" className="text-amber-600 hover:underline">
              Voltar ao início
            </a>
          </div>
        </section>

        {/* Nossa proposta */}
        <section id="proposta" className="bg-amber-100 py-12 px-4 md:px-16">
          <h2 className="text-3xl md:text-4xl font-semibold text-amber-900 mb-4 text-center">
            Nossa proposta
          </h2>
          <p className="max-w-3xl mx-auto text-center text-amber-800 mb-4">
            Rosales Café: a proposta de um café brasileiro com o estilo e a inspiração colombiana. Um convite a descobrir o café com atenção aos detalhes.
          </p>
          <p className="max-w-3xl mx-auto text-center text-amber-800">
            Uma identidade entre duas culturas do café.
          </p>
          <div className="text-center mt-6">
            <a href="#inicio" className="text-amber-600 hover:underline">
              Voltar ao início
            </a>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="bg-amber-200 py-6 text-center">
        <p className="text-amber-800">&copy; Rosales Café</p>
      </footer>
    </div>
  );
}