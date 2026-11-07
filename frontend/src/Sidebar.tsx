import { Menu } from './notes';
import type { Page } from './types';

function HomeIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <path d="M3.5 9 10 3.5 16.5 9v7a.5.5 0 0 1-.5.5h-3.5v-5h-5v5H4a.5.5 0 0 1-.5-.5Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

function PageIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <path d="M5 2.75h6.5L15.25 6.5v10.75H5Z M11.5 2.75V6.5h3.75 M7.5 10h5 M7.5 13h5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

export default function Sidebar({ pages, currentId, onHome, open, onClose, onNewPage, onDeletePage }: {
  pages: Page[];
  currentId: string | null;
  onHome: boolean;
  open: boolean;
  onClose: () => void;
  onNewPage: () => void;
  onDeletePage: (page: Page) => void;
}) {
  return (
    <>
      <nav className={`sidebar${open ? ' open' : ''}`} aria-label="Pages">
        <a className="sidebar-workspace" href="#/" onClick={onClose}>
          <span className="workspace-badge" aria-hidden="true">W</span>
          LaTeX Lecture
        </a>
        <a className={`sidebar-item${onHome ? ' active' : ''}`} href="#/home" onClick={onClose}>
          <HomeIcon /> Home
        </a>

        <div className="sidebar-heading">Lectures</div>
        {pages.map((page) => (
          <div className={`sidebar-page${page.id === currentId ? ' active' : ''}`} key={page.id}>
            <a className="sidebar-item" href={`#/page/${page.id}`} onClick={onClose}>
              <PageIcon />
              <span className="sidebar-label">{page.title || 'Untitled lecture'}</span>
            </a>
            <Menu label={`Actions for ${page.title || 'Untitled lecture'}`} className="sidebar-menu">
              {(close) => (
                <button type="button" role="menuitem" className="danger" onClick={() => { close(); onDeletePage(page); }}>
                  Delete
                </button>
              )}
            </Menu>
          </div>
        ))}
        <button type="button" className="sidebar-item sidebar-new" onClick={() => { onClose(); onNewPage(); }}>
          <span className="sidebar-plus" aria-hidden="true">+</span> New page
        </button>
      </nav>
      {open && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
    </>
  );
}
