import React from 'react';

function Header() {
  return (
    <header className="bg-white shadow-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center h-16">
        <div className="text-2xl font-bold text-gray-900">
          Rosales Café
        </div>
        <nav className="space-x-6">
          <a href="#hero" className="text-gray-700 hover:text-gray-900 transition-colors duration-200">
            Início
          </a>
          <a href="#story" className="text-gray-700 hover:text-gray-900 transition-colors duration-200">
            Sobre
          </a>
          <a href="#contact" className="text-gray-700 hover:text-gray-900 transition-colors duration-200">
            Contato
          </a>
        </nav>
      </div>
    </header>
  );
}

export default Header;