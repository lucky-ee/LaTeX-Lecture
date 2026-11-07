import type { Note, Page } from './types';

const PAGES_KEY = 'wispr-lecture:pages';
// Before pages existed, there was a single list of notes and a title.
const OLD_NOTES_KEY = 'wispr-lecture:notes';
const OLD_TITLE_KEY = 'wispr-lecture:title';

export function newId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// A note still loading when the page closed will never finish; offer a retry instead.
function settle(notes: Note[]): Note[] {
  return notes.map((note) => (note.status === 'loading' ? { ...note, status: 'error' } : note));
}

// Storage can be unavailable (private windows, blocked site data), so every
// access is guarded and the app still works without it.
export function loadPages(): Page[] {
  try {
    const saved = localStorage.getItem(PAGES_KEY);
    if (saved !== null) {
      const pages: Page[] = JSON.parse(saved);
      return Array.isArray(pages) ? pages.map((page) => ({ ...page, notes: settle(page.notes ?? []) })) : [];
    }

    const notes: Note[] = JSON.parse(localStorage.getItem(OLD_NOTES_KEY) ?? '[]');
    const title = localStorage.getItem(OLD_TITLE_KEY) ?? '';
    if (!Array.isArray(notes) || (notes.length === 0 && !title)) return [];
    const now = Date.now();
    return [{ id: newId(), title, notes: settle(notes), createdAt: now, updatedAt: now }];
  } catch {
    return [];
  }
}

export function savePages(pages: Page[]) {
  try {
    localStorage.setItem(PAGES_KEY, JSON.stringify(pages));
    localStorage.removeItem(OLD_NOTES_KEY);
    localStorage.removeItem(OLD_TITLE_KEY);
  } catch {
    // Pages still work for this session; they just won't survive a refresh.
  }
}
