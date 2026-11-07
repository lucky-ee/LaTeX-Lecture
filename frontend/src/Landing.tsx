import { MathView } from './notes';

const examples = [
  {
    spoken: 'for all epsilon greater than zero there exists delta greater than zero',
    latex: String.raw`\forall \varepsilon > 0,\ \exists \delta > 0`,
  },
  { spoken: 'the integral from a to b of one over x', latex: String.raw`\int_a^b \frac{1}{x}\,dx` },
  {
    spoken: 'the limit as n goes to infinity of one over n squared',
    latex: String.raw`\lim_{n \to \infty} \frac{1}{n^2}`,
  },
];

const features = [
  {
    title: 'Speak naturally',
    body: 'Dictate the way your professor talks. Wispr Lecture takes the transcription from Wispr Flow, or anything you type, and turns the math into notation.',
  },
  {
    title: 'You decide when it’s ambiguous',
    body: 'Does “one plus x squared over two” mean the whole thing over two? When a phrase has more than one reading, you pick the right one.',
  },
  {
    title: 'Faithful, not clever',
    body: 'It writes down what was said. It doesn’t solve problems, fix claims or fill in missing assumptions.',
  },
  {
    title: 'Take it anywhere',
    body: 'Copy any note as LaTeX and paste it into Overleaf, Obsidian or Notion.',
  },
];

export default function Landing({ hasPages, onStart }: { hasPages: boolean; onStart: () => void }) {
  return (
    <div className="landing">
      <nav className="landing-nav">
        <span className="landing-logo">Wispr Lecture</span>
        <a className="landing-nav-link" href="#/home">Open app</a>
      </nav>

      <header className="hero">
        <h1>Math notes that keep up with the lecture.</h1>
        <p>
          Say it out loud and get clean mathematical notation. Built for students taking notes in
          university math lectures.
        </p>
        <div className="hero-actions">
          <button type="button" className="cta" onClick={onStart}>
            {hasPages ? 'Open your notes' : 'Start a lecture page'}
          </button>
          <span className="hero-note">No account needed. Notes stay in your browser.</span>
        </div>
      </header>

      <section className="demo" aria-label="Examples">
        {examples.map((example) => (
          <div className="demo-row" key={example.spoken}>
            <span className="demo-spoken">“{example.spoken}”</span>
            <span className="demo-arrow" aria-hidden="true">→</span>
            <span className="demo-math"><MathView latex={example.latex} /></span>
          </div>
        ))}
        <div className="demo-row">
          <span className="demo-spoken">“(1 + x^2) / 2”</span>
          <span className="demo-arrow" aria-hidden="true">→</span>
          <span className="demo-math demo-choice">
            <span className="choice"><MathView latex={String.raw`\frac{1+x^2}{2}`} /></span>
            <span className="demo-or">or</span>
            <span className="choice"><MathView latex={String.raw`1+\frac{x^2}{2}`} /></span>
          </span>
        </div>
      </section>

      <section className="features">
        {features.map((feature) => (
          <div className="feature" key={feature.title}>
            <h3>{feature.title}</h3>
            <p>{feature.body}</p>
          </div>
        ))}
      </section>

      <section className="closing">
        <h2>Your next lecture starts here.</h2>
        <button type="button" className="cta" onClick={onStart}>
          {hasPages ? 'Open your notes' : 'Start a lecture page'}
        </button>
      </section>

      <footer className="landing-footer">
        Independent project · Not affiliated with or endorsed by Wispr
      </footer>
    </div>
  );
}
