import { useEffect, useRef, useState } from 'react';
import { apiUrl } from './config';
import Home from './Home';
import Landing from './Landing';
import { noteToLatex } from './notes';
import PageView from './PageView';
import Sidebar from './Sidebar';
import { loadPages, newId, savePages } from './storage';
import type { Note, Page, Segment } from './types';

type Route = { name: 'landing' } | { name: 'home' } | { name: 'page'; id: string };

// Routes live in the URL hash (#/home, #/page/<id>) so the app works on any
// static host without server-side rewrites.
function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, '');
  if (path === '/home') return { name: 'home' };
  const page = path.match(/^\/page\/([\w-]+)$/);
  if (page) return { name: 'page', id: page[1] };
  return { name: 'landing' };
}

function useRoute() {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const update = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  return route;
}

function go(hash: string) {
  window.location.hash = hash;
}

export default function App() {
  const route = useRoute();
  const [pages, setPages] = useState<Page[]>(loadPages);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const nextNoteId = useRef(
    pages.reduce((max, page) => page.notes.reduce((m, note) => Math.max(m, note.id), max), 0),
  );

  useEffect(() => savePages(pages), [pages]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const current = route.name === 'page' ? pages.find((page) => page.id === route.id) ?? null : null;

  useEffect(() => {
    document.title = current ? `${current.title || 'Untitled lecture'} · LaTeX Lecture` : 'LaTeX Lecture';
  }, [current]);

  function updatePage(id: string, change: (page: Page) => Page) {
    setPages((previous) => previous.map((page) => (page.id === id ? { ...change(page), updatedAt: Date.now() } : page)));
  }

  function updateNote(pageId: string, noteId: number, change: (note: Note) => Note) {
    updatePage(pageId, (page) => ({ ...page, notes: page.notes.map((note) => (note.id === noteId ? change(note) : note)) }));
  }

  async function interpret(pageId: string, noteId: number, text: string) {
    updateNote(pageId, noteId, (note) => ({ ...note, status: 'loading' }));
    try {
      const response = await fetch(apiUrl('/api/interpret'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result: { segments: Segment[] } = await response.json();
      if (!Array.isArray(result.segments)) throw new Error('Invalid AI response');

      updateNote(pageId, noteId, (note) => ({ ...note, status: 'ready', segments: result.segments }));
    } catch (error) {
      console.error('Interpretation failed:', error);
      // Keep the original transcription even if the API fails.
      updateNote(pageId, noteId, (note) => ({ ...note, status: 'error' }));
    }
  }

  function newPage() {
    const now = Date.now();
    const page: Page = { id: newId(), title: '', notes: [], createdAt: now, updatedAt: now };
    setPages((previous) => [...previous, page]);
    go(`/page/${page.id}`);
  }

  function deletePage(page: Page) {
    const name = page.title || 'Untitled lecture';
    if (!window.confirm(`Delete “${name}” and its ${page.notes.length} notes? This can’t be undone.`)) return;
    setPages((previous) => previous.filter((p) => p.id !== page.id));
    if (route.name === 'page' && route.id === page.id) go('/home');
  }

  function addNote(pageId: string, text: string) {
    const id = ++nextNoteId.current;
    updatePage(pageId, (page) => ({
      ...page,
      notes: [...page.notes, { id, original: text, segments: null, status: 'loading' }],
    }));
    void interpret(pageId, id, text);
  }

  async function copy(note: Note) {
    try {
      await navigator.clipboard.writeText(noteToLatex(note));
      setToast('Copied to clipboard');
    } catch {
      setToast('Could not copy');
    }
  }

  if (route.name === 'landing') {
    return <Landing hasPages={pages.length > 0} onStart={() => (pages.length > 0 ? go('/home') : newPage())} />;
  }

  return (
    <div className="app">
      <Sidebar
        pages={pages}
        currentId={current?.id ?? null}
        onHome={route.name === 'home'}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewPage={newPage}
        onDeletePage={deletePage}
      />

      <div className="main">
        <header className="topbar">
          <button type="button" className="sidebar-toggle" aria-label="Open sidebar" onClick={() => setSidebarOpen(true)}>
            ☰
          </button>
          <span className="breadcrumb">
            <a href="#/home">Home</a>
            {route.name === 'page' && (
              <>
                <span className="breadcrumb-sep">/</span>
                <span className="breadcrumb-current">{current ? current.title || 'Untitled lecture' : 'Not found'}</span>
              </>
            )}
          </span>
          {current && (
            <span className="topbar-meta">
              {current.notes.length} {current.notes.length === 1 ? 'note' : 'notes'}
            </span>
          )}
        </header>

        {route.name === 'home' && <Home pages={pages} onNewPage={newPage} onDeletePage={deletePage} />}

        {route.name === 'page' && current && (
          <PageView
            key={current.id}
            page={current}
            onRename={(title) => updatePage(current.id, (page) => ({ ...page, title }))}
            onAddNote={(text) => addNote(current.id, text)}
            onChoose={(noteId, index, latex) =>
              updateNote(current.id, noteId, (note) => ({
                ...note,
                segments: note.segments?.map((segment, i) => (i === index ? { ...segment, chosen: latex } : segment)) ?? null,
              }))
            }
            onCopy={(note) => void copy(note)}
            onRetry={(note) => void interpret(current.id, note.id, note.original)}
            onDeleteNote={(noteId) =>
              updatePage(current.id, (page) => ({ ...page, notes: page.notes.filter((note) => note.id !== noteId) }))
            }
          />
        )}

        {route.name === 'page' && !current && (
          <div className="page">
            <h1 className="page-title-static">This page doesn’t exist</h1>
            <p className="empty">It may have been deleted. <a href="#/home">Go to Home</a></p>
          </div>
        )}

        <footer className="app-footer">Independent feature prototype · Not affiliated with Wispr</footer>
      </div>

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
