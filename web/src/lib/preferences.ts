import { create } from "zustand";
import { MESH } from "./mesh";

const DISPLAY_KEY = "rcash.displayCurrency";

interface Preferences {
  displayCurrency: string;
  setDisplayCurrency: (code: string) => void;
}

/** The default is USD; each browser can override it without on-chain state. */
export const usePreferences = create<Preferences>((set) => ({
  displayCurrency: localStorage.getItem(DISPLAY_KEY) ?? MESH.defaultCurrency,
  setDisplayCurrency: (code) => {
    localStorage.setItem(DISPLAY_KEY, code);
    set({ displayCurrency: code });
  },
}));
