import React from 'react';

function Footer() {
  return (
    <footer className="bg-gray-800 text-gray-200 py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <p className="text-sm">
          © {new Date().getFullYear()} Rosales Café. Todos os direitos reservados.
        </p>
      </div>
    </footer>
  );
}

export default Footer;