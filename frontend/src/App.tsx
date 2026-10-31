import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import katex from 'katex';

type Segment = {
  kind: 'text' | 'math';
  content: string;
  readings: string[];
};

type Note = {
  id: number;
  original: string;
  segments: Segment[] | null;
  status: 'loading' | 'ready' | 'error';
};

// KaTeX renders into a DOM element. React still owns the rest of the interface.
function MathView({ latex }: { latex: string }) {
  const element = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!element.current) return;
    try {
      katex.render(latex, element.current, { throwOnError: true, trust: false });
    } catch {
      element.current.textContent = latex;
      element.current.title = 'Could not render this LaTeX';
    }
  }, [latex]);

  return <span ref={element} className="math" />;
}

function MathSegment({ segment }: { segment: Segment }) {
  const [chosen, setChosen] = useState<string | null>(null);
  const options = [...new Set(segment.readings.filter(Boolean))].slice(0, 3);

  if (options.length === 0) return <span>{segment.content}</span>;
  if (chosen !== null) return <MathView latex={chosen} />;
  if (options.length === 1) return <MathView latex={options[0]} />;

  return (
    <span className="choices" aria-label="Choose the intended equation">
      <span className="choice-label">Choose equation:</span>
      {options.map((latex, index) => (
        <button
          className="choice"
          type="button"
          key={latex}
          onClick={() => setChosen(latex)}
          aria-label={`Choose reading ${index + 1}`}
        >
          <MathView latex={latex} />
        </button>
      ))}
    </span>
  );
}

function NoteContent({ note }: { note: Note }) {
  if (!note.segments || note.segments.length === 0) {
    return <span>{note.original}</span>;
  }

  return (
    <>
      {note.segments.map((segment, index) =>
        segment.kind === 'math' ? (
          <MathSegment segment={segment} key={index} />
        ) : (
          <span key={index}>{segment.content}</span>
        ),
      )}
    </>
  );
}

export default function App() {
  const [draft, setDraft] = useState('');
  const [notes, setNotes] = useState<Note[]>([]);
  const nextId = useRef(0);

  async function addNote() {
    const original = draft.trim();
    if (!original) return;

    const id = ++nextId.current;
    setDraft('');
    setNotes((previous) => [
      ...previous,
      { id, original, segments: null, status: 'loading' },
    ]);

    try {
      const response = await fetch('/api/interpret', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: original }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result: { segments: Segment[] } = await response.json();
      if (!Array.isArray(result.segments)) throw new Error('Invalid AI response');

      setNotes((previous) =>
        previous.map((note) =>
          note.id === id ? { ...note, status: 'ready', segments: result.segments } : note,
        ),
      );
    } catch (error) {
      console.error('Interpretation failed:', error);
      // Keep the original transcription even if the API fails.
      setNotes((previous) =>
        previous.map((note) =>
          note.id === id ? { ...note, status: 'error' } : note,
        ),
      );
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void addNote();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <main className="page">
      <header className="header">
        <span className="eyebrow">VOICE-FIRST MATHEMATICS</span>
        <h1>Wispr Lecture <span className="prototype">Prototype</span></h1>
        <p>Speak naturally. Keep the meaning. Choose when notation is ambiguous.</p>
      </header>

      <section className="notebook" aria-label="Lecture notes">
        <div className="notebook-heading">
          <h2>Lecture notes</h2>
          <span>{notes.length} {notes.length === 1 ? 'note' : 'notes'}</span>
        </div>
        {notes.length === 0 ? (
          <p className="empty">Your notes will appear here. Try an integral, limit, or proof statement.</p>
        ) : (
          <ol className="notes" aria-live="polite">
            {notes.map((note) => (
              <li key={note.id} className="note">
                <div className="note-body"><NoteContent note={note} /></div>
                {note.status === 'loading' && <p className="note-meta">Interpreting…</p>}
                {note.status === 'error' && (
                  <p className="note-meta warning">AI unavailable — original text kept.</p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <form className="composer" onSubmit={submit}>
        <label htmlFor="dictation">Dictate or type a note</label>
        <textarea
          id="dictation"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. for all epsilon greater than zero there exists delta greater than zero"
          rows={3}
          maxLength={2000}
        />
        <div className="composer-bottom">
          <span>Enter to add · Shift+Enter for a new line</span>
          <button type="submit" className="submit" disabled={!draft.trim()}>Add note</button>
        </div>
      </form>

      <footer>Independent feature prototype · Not affiliated with Wispr</footer>
    </main>
  );
}