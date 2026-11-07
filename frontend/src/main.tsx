import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';
import 'katex/dist/katex.min.css';
// Copying selected math puts its LaTeX (wrapped in $...$) on the clipboard
// instead of KaTeX's hidden accessibility markup.
import 'katex/contrib/copy-tex';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);