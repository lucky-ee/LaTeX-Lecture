import { useEffect, useRef, useState, type ReactNode } from 'react';
import katex from 'katex';
import type { Note, Segment } from './types';

export function readingOptions(segment: Segment) {
  return [...new Set(segment.readings.filter(Boolean))].slice(0, 3);
}

// Plain text with $...$ around math, ready to paste into Overleaf, Obsidian or Notion.
export function noteToLatex(note: Note) {
  if (!note.segments || note.segments.length === 0) return note.original;
  return note.segments
    .map((segment) => {
      const options = readingOptions(segment);
      if (segment.kind !== 'math' || options.length === 0) return segment.content;
      return `$${segment.chosen ?? options[0]}$`;
    })
    .join('');
}

// KaTeX renders into a DOM element. React still owns the rest of the interface.
export function MathView({ latex }: { latex: string }) {
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

function MathSegment({ segment, onChoose }: { segment: Segment; onChoose: (latex: string | undefined) => void }) {
  const options = readingOptions(segment);

  if (options.length === 0) return <span>{segment.content}</span>;
  if (options.length === 1) return <MathView latex={options[0]} />;
  if (segment.chosen !== undefined) {
    return (
      <span className="chosen">
        <MathView latex={segment.chosen} />
        <button type="button" className="change" onClick={() => onChoose(undefined)}>
          Change
        </button>
      </span>
    );
  }

  return (
    <span className="choices" role="group" aria-label="Choose the intended equation">
      <span className="choice-label">
        Which did you mean? <span className="choice-source">“{segment.content}”</span>
      </span>
      <span className="choice-options">
        {options.map((latex, index) => (
          <button
            className="choice"
            type="button"
            key={latex}
            onClick={() => onChoose(latex)}
            aria-label={`Choose reading ${index + 1}`}
          >
            <MathView latex={latex} />
          </button>
        ))}
      </span>
    </span>
  );
}

export function NoteContent({ note, onChoose }: {
  note: Note;
  onChoose: (index: number, latex: string | undefined) => void;
}) {
  if (!note.segments || note.segments.length === 0) {
    return <span>{note.original}</span>;
  }

  return (
    <>
      {note.segments.map((segment, index) =>
        segment.kind === 'math' ? (
          <MathSegment segment={segment} key={index} onChoose={(latex) => onChoose(index, latex)} />
        ) : (
          <span key={index}>{segment.content}</span>
        ),
      )}
    </>
  );
}

// A small dropdown that closes on outside click or Escape.
export function Menu({ label, className = '', children }: {
  label: string;
  className?: string;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  return (
    <div className={`menu-root ${className}${open ? ' open' : ''}`} ref={root}>
      <button
        type="button"
        className="handle"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        ⋮⋮
      </button>
      {open && <div className="menu" role="menu">{children(() => setOpen(false))}</div>}
    </div>
  );
}

export function NoteMenu({ note, onCopy, onRetry, onDelete }: {
  note: Note;
  onCopy: () => void;
  onRetry: () => void;
  onDelete: () => void;
}) {
  return (
    <Menu label="Note actions" className="block-menu">
      {(close) => {
        const run = (action: () => void) => () => { close(); action(); };
        return (
          <>
            <button type="button" role="menuitem" onClick={run(onCopy)}>Copy as LaTeX</button>
            {note.status !== 'loading' && (
              <button type="button" role="menuitem" onClick={run(onRetry)}>Interpret again</button>
            )}
            <div className="menu-divider" />
            <button type="button" role="menuitem" className="danger" onClick={run(onDelete)}>Delete</button>
          </>
        );
      }}
    </Menu>
  );
}
