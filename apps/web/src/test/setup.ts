import "@testing-library/jest-dom";

// jsdom's default window doesn't always expose localStorage in
// vitest 3 + jsdom 25 — provide a tiny in-memory shim so components
// that touch window.localStorage during tests don't crash.
if (typeof globalThis.localStorage === "undefined" && typeof globalThis.window !== "undefined") {
  let store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear() {
      store = new Map();
    },
    getItem(key: string) {
      return store.has(key) ? (store.get(key) as string) : null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
  };
  Object.defineProperty(globalThis.window, "localStorage", {
    value: storage,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(globalThis, "localStorage", {
    value: storage,
    configurable: true,
    writable: true,
  });
}
