export type Segment = {
  kind: 'text' | 'math';
  content: string;
  readings: string[];
  // The reading the user picked when there was more than one. Client-side only.
  chosen?: string;
};

export type Note = {
  id: number;
  original: string;
  segments: Segment[] | null;
  status: 'loading' | 'ready' | 'error';
};

export type Page = {
  id: string;
  title: string;
  notes: Note[];
  createdAt: number;
  updatedAt: number;
};
