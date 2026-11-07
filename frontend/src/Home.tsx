import type { Page } from './types';

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });

export function editedAgo(timestamp: number) {
  const minutes = Math.round((timestamp - Date.now()) / 60000);
  if (minutes > -1) return 'Edited just now';
  if (minutes > -60) return `Edited ${relative.format(minutes, 'minute')}`;
  const hours = Math.round(minutes / 60);
  if (hours > -24) return `Edited ${relative.format(hours, 'hour')}`;
  return `Edited ${relative.format(Math.round(hours / 24), 'day')}`;
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function Home({ pages, onNewPage, onDeletePage }: {
  pages: Page[];
  onNewPage: () => void;
  onDeletePage: (page: Page) => void;
}) {
  const recent = [...pages].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <div className="page home">
      <h1 className="home-greeting">{greeting()}</h1>
      <h2 className="home-section">Your lectures</h2>
      <div className="cards">
        {recent.map((page) => (
          <div className="card" key={page.id}>
            <a className="card-link" href={`#/page/${page.id}`}>
              <span className="card-cover" aria-hidden="true" />
              <span className="card-title">{page.title || 'Untitled lecture'}</span>
              <span className="card-preview">{page.notes[0]?.original ?? 'No notes yet'}</span>
              <span className="card-meta">
                {page.notes.length} {page.notes.length === 1 ? 'note' : 'notes'} · {editedAgo(page.updatedAt)}
              </span>
            </a>
            <button
              type="button"
              className="card-delete"
              aria-label={`Delete ${page.title || 'Untitled lecture'}`}
              onClick={() => onDeletePage(page)}
            >
              Delete
            </button>
          </div>
        ))}
        <button type="button" className="card card-new" onClick={onNewPage}>
          <span className="card-plus" aria-hidden="true">+</span>
          New page
        </button>
      </div>
      {pages.length === 0 && (
        <p className="empty">No lectures yet. Start a new page for your next lecture.</p>
      )}
    </div>
  );
}
