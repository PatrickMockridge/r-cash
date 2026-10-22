// IndexedDB storage for encrypted keystores and the local activity journal.
// No plaintext secret, mnemonic or password is ever written here.

const DB_NAME = "rcash";
const DB_VERSION = 1;

export interface StoredKeystore {
  address: string;
  document: string;
  createdAt: number;
}

export interface JournalEntry {
  id: string;
  kind: string;
  deployId?: string;
  summary: string;
  createdAt: number;
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("keystores")) {
        db.createObjectStore("keystores", { keyPath: "address" });
      }
      if (!db.objectStoreNames.contains("journal")) {
        db.createObjectStore("journal", { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transaction<T>(
  store: string,
  mode: IDBTransactionMode,
  run: (objectStore: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const request = run(tx.objectStore(store));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    tx.oncomplete = () => db.close();
  });
}

export function saveKeystore(address: string, document: string): Promise<unknown> {
  const entry: StoredKeystore = { address, document, createdAt: Date.now() };
  return transaction("keystores", "readwrite", (store) => store.put(entry));
}

export function loadKeystore(address: string): Promise<StoredKeystore | undefined> {
  return transaction("keystores", "readonly", (store) => store.get(address));
}

export function listKeystores(): Promise<StoredKeystore[]> {
  return transaction("keystores", "readonly", (store) => store.getAll());
}

export function addJournal(entry: JournalEntry): Promise<unknown> {
  return transaction("journal", "readwrite", (store) => store.put(entry));
}

export function listJournal(): Promise<JournalEntry[]> {
  return transaction("journal", "readonly", (store) => store.getAll());
}
