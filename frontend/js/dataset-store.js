/**
 * js/dataset-store.js
 * Shared dataset-selection state backed by localStorage so app.js and
 * modals.js/dataset-picker.js always agree on the active data source.
 * Modes: 'hybrid' | 'synthetic' | 'custom'
 */

const STORAGE_KEY = 'pharma.dataset.selection.v1';
const VALID_MODES = ['hybrid', 'synthetic', 'custom'];

const listeners = new Set();
let cache = null;

export const DEFAULT_SELECTION = Object.freeze({ mode: 'hybrid', filename: null });

function parse(raw) {
  try {
    const parsed = JSON.parse(raw);
    if (parsed && VALID_MODES.includes(parsed.mode)) {
      return { mode: parsed.mode, filename: parsed.filename || null };
    }
  } catch (_) {}
  return null;
}

function read() {
  try {
    const parsed = parse(localStorage.getItem(STORAGE_KEY));
    if (parsed) return parsed;
  } catch (_) {}
  return { ...DEFAULT_SELECTION };
}

export function getDatasetSelection() {
  if (!cache) cache = read();
  return { ...cache };
}

export function setDatasetSelection(selection) {
  const next = { mode: selection.mode, filename: selection.filename || null };
  cache = next;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch (_) {}
  listeners.forEach((cb) => cb(getDatasetSelection()));
}

export function onDatasetSelectionChange(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function datasetLabel(selection) {
  if (selection.mode === 'custom') return selection.filename || 'Custom Dataset';
  return selection.mode === 'synthetic' ? 'Synthetic' : 'Hybrid CMS';
}