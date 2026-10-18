import React from 'react';

function Hero() {
  return (
    <section id="hero" className="w-full bg-gradient-to-br from-yellow-300 to-yellow-100 py-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold text-gray-900 mb-4">
          Rosales Café – Café brasileiro, inspiração colombiana
        </h1>
        <p className="text-lg sm:text-xl text-gray-700 mb-8">
          Sabores autênticos, aromas irresistíveis e uma experiência única que celebra a riqueza da cultura do café.
        </p>
        <a
          href="#contact"
          className="inline-block bg-blue-600 text-white px-8 py-3 rounded-lg shadow-md hover:bg-blue-700 transition-colors duration-200 transform hover:scale-105"
        >
          Visite-nos
        </a>
      </div>
    </section>
  );
}

export default Hero;