/**
 * "Folders" — saved conversation filters.
 *
 * Purely a client-side convenience: a folder is just a name plus the query
 * string of the conversation list, persisted to `localStorage` and listed in
 * the left rail.
 */
import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "chattysup.folders";
const CHANGE_EVENT = "chattysup:folders";

export interface SavedFolder {
  id: string;
  name: string;
  /** Serialised `URLSearchParams` for `/conversations`. */
  query: string;
}

function read(): SavedFolder[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as SavedFolder[]) : [];
  } catch {
    return [];
  }
}

function write(folders: SavedFolder[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(folders));
  } catch {
    /* storage unavailable — folders simply do not persist */
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

/** Read/write access to the saved folders, kept in sync across components. */
export function useFolders() {
  const [folders, setFolders] = useState<SavedFolder[]>(read);

  useEffect(() => {
    const sync = () => setFolders(read());
    window.addEventListener(CHANGE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CHANGE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const add = useCallback((name: string, query: string) => {
    const folder: SavedFolder = {
      id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      name,
      query,
    };
    write([...read(), folder]);
    return folder;
  }, []);

  const remove = useCallback((id: string) => {
    write(read().filter((folder) => folder.id !== id));
  }, []);

  const rename = useCallback((id: string, name: string) => {
    write(read().map((folder) => (folder.id === id ? { ...folder, name } : folder)));
  }, []);

  return { folders, add, remove, rename };
}
