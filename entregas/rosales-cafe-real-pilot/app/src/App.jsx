import React from 'react';
import Header from './components/Header';
import Hero from './components/Hero';
import Story from './components/Story';
import Footer from './components/Footer';

function App() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <Header />
      <main className="flex-1">
        <Hero />
        <Story />
      </main>
      <Footer />
    </div>
  );
}

export default App;