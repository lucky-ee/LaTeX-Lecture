import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { NoteContent, NoteMenu } from './notes';
import StageMetrics from './StageMetrics';
import type { Note, Page } from './types';

// Grow a textarea with its content, like a Notion text block. scrollHeight
// excludes the border, so add it back or a scrollbar appears.
function autoGrow(element: HTMLTextAreaElement | null) {
  if (!element) return;
  element.style.height = 'auto';
  element.style.height = `${element.scrollHeight + element.offsetHeight - element.clientHeight}px`;
}

export default function PageView({ page, onRename, onAddNote, onChoose, onCopy, onRetry, onDeleteNote }: {
  page: Page;
  onRename: (title: string) => void;
  onAddNote: (text: string) => void;
  onChoose: (noteId: number, index: number, latex: string | undefined) => void;
  onCopy: (note: Note) => void;
  onRetry: (note: Note) => void;
  onDeleteNote: (noteId: number) => void;
}) {
  const [draft, setDraft] = useState('');
  const composer = useRef<HTMLTextAreaElement>(null);
  const titleField = useRef<HTMLTextAreaElement>(null);
  const isNew = page.notes.length === 0 && !page.title;

  useEffect(() => autoGrow(composer.current), [draft]);
  useEffect(() => autoGrow(titleField.current), [page.title]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    onAddNote(text);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <div className="page">
      <textarea
        className="page-title"
        ref={titleField}
        value={page.title}
        onChange={(event) => onRename(event.target.value.replace(/\n/g, ''))}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            composer.current?.focus();
          }
        }}
        placeholder="Untitled lecture"
        aria-label="Lecture title"
        rows={1}
        autoFocus={isNew}
      />

      <section className="notebook" aria-label="Lecture notes">
        {page.notes.length === 0 ? (
          <p className="empty">Your notes will appear here. Try an integral, limit, or proof statement.</p>
        ) : (
          <ol className="notes" aria-live="polite">
            {page.notes.map((note) => (
              <li key={note.id} className="block">
                <NoteMenu
                  note={note}
                  onCopy={() => onCopy(note)}
                  onRetry={() => onRetry(note)}
                  onDelete={() => onDeleteNote(note.id)}
                />
                <div className="block-body">
                  <NoteContent note={note} onChoose={(index, latex) => onChoose(note.id, index, latex)} />
                </div>
                {note.status === 'loading' && <p className="block-meta loading">Interpreting…</p>}
                {note.status === 'error' && (
                  <p className="block-meta warning">
                    AI unavailable — original text kept.
                    <button type="button" className="link" onClick={() => onRetry(note)}>Retry</button>
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <form className="composer" onSubmit={submit}>
        <label htmlFor="dictation" className="visually-hidden">Dictate or type a note</label>
        <textarea
          id="dictation"
          ref={composer}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Dictate or type a note… e.g. for all epsilon greater than zero there exists delta greater than zero"
          rows={1}
          maxLength={2000}
        />
        <div className="composer-bottom">
          <span>Enter to add · Shift+Enter for a new line</span>
          <button type="submit" className="submit" disabled={!draft.trim()}>Add note</button>
        </div>
      </form>

      <StageMetrics />
    </div>
  );
}
