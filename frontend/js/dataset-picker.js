/**
 * js/dataset-picker.js
 * Dataset selector: header trigger button + "Choose Dataset" picker modal.
 * Supports Synthetic / Hybrid CMS one-click selection and an in-modal
 * Upload → Processing → Success/Failure flow for custom datasets.
 */

import { openModal, closeModal } from './modals.js';
import { State, processCustomDataset } from './data-loader.js';
import {
  getDatasetSelection,
  setDatasetSelection,
  onDatasetSelectionChange,
  datasetLabel,
} from './dataset-store.js';

const STEPS = [
  { id: 'inspect', icon: '🔍', name: 'Column Inspection', defaultDetail: 'Scanning required vs missing columns' },
  { id: 'synthesize', icon: '🧪', name: 'Auto-Synthesis', defaultDetail: 'Gamma (fills), Poisson (samples), Normal (calls)' },
  { id: 'features', icon: '⚙️', name: 'Derived Features', defaultDetail: 'Cadence & Sample Ratio calculations' },
  { id: 'ml', icon: '🤖', name: 'ML Driver Attribution', defaultDetail: 'Model driver attribution & lift' },
];

function els() {
  return {
    btn: document.getElementById('dataset-picker-btn'),
    label: document.getElementById('dataset-picker-label'),
    modal: document.getElementById('dataset-modal'),
    fileInput: document.getElementById('custom-file-input'),
    pickerView: document.getElementById('dataset-picker-view'),
    processView: document.getElementById('dataset-processing-view'),
    processFilename: document.getElementById('dataset-process-filename'),
    processFill: document.getElementById('dataset-process-fill'),
    processError: document.getElementById('dataset-process-error'),
    processStatus: document.getElementById('dataset-process-status-title'),
    stepsContainer: document.getElementById('dataset-process-steps'),
    doneView: document.getElementById('dataset-done-view'),
    closeBtn: document.getElementById('dataset-modal-close'),
    cancelBtn: document.getElementById('dataset-upload-cancel'),
  };
}

let running = false;
let aborted = false;
let confirming = false;
const stageStates = STEPS.map(() => 'pending');

export function renderDatasetTriggerLabel() {
  const el = document.getElementById('dataset-picker-label');
  if (el) el.textContent = `Dataset: ${datasetLabel(getDatasetSelection())}`;
}

function showPickerView() {
  const { pickerView, processView } = els();
  running = false;
  aborted = false;
  confirming = false;
  if (pickerView) pickerView.hidden = false;
  if (processView) processView.hidden = true;
}

function showProcessingView(fileName) {
  const {
    pickerView, processView, stepsContainer, doneView,
    processFilename, processFill, processError, processStatus, cancelBtn,
  } = els();
  running = true;
  aborted = false;
  confirming = false;
  if (pickerView) pickerView.hidden = true;
  if (processView) processView.hidden = false;
  if (stepsContainer) stepsContainer.hidden = false;
  if (doneView) doneView.hidden = true;
  if (processFilename) processFilename.textContent = fileName;
  if (processFill) processFill.style.width = '0%';
  if (processError) {
    processError.hidden = true;
    processError.textContent = '';
  }
  if (processStatus) processStatus.textContent = 'Processing Dataset';
  if (cancelBtn) cancelBtn.hidden = false;
  elStep(undefined, 'reset');
}

function stageIndex(stepId) {
  return STEPS.findIndex((s) => s.id === stepId);
}

function renderStages() {
  STEPS.forEach((s, i) => {
    const stepEl = document.getElementById(`dp-step-${s.id}`);
    const statusEl = document.getElementById(`dp-step-${s.id}-status`);
    const iconEl = stepEl ? stepEl.querySelector('.step-icon') : null;
    if (!stepEl) return;
    stepEl.classList.remove('pending', 'active', 'completed');
    stepEl.classList.add(stageStates[i]);
    if (statusEl) {
      statusEl.textContent =
        stageStates[i] === 'done' ? '✓ Done' : stageStates[i] === 'active' ? 'In Progress…' : 'Pending';
    }
    if (iconEl) {
      iconEl.textContent = stageStates[i] === 'done' ? '✓' : s.icon;
    }
  });
}

/**
 * Render a single stage-progress event into the three-state model
 * (pending / active / done). Every stage before the reported one in the
 * pipeline sequence is marked done, so finished stages never fall back to
 * "Pending" and events that arrive out of order are still handled.
 */
function elStep(stepId, status, detail) {
  if (status === 'reset') {
    stageStates.fill('pending');
    STEPS.forEach((s) => {
      const detailEl = document.getElementById(`dp-step-${s.id}-detail`);
      if (detailEl) detailEl.textContent = s.defaultDetail;
    });
    renderStages();
    return;
  }

  const i = stageIndex(stepId);
  if (i === -1) return;

  if (status === 'completed') {
    stageStates[i] = 'done';
    for (let j = 0; j < i; j++) stageStates[j] = 'done';
  } else if (status === 'active') {
    if (stageStates[i] !== 'done') stageStates[i] = 'active';
    for (let j = 0; j < i; j++) stageStates[j] = 'done';
  }

  renderStages();

  const detailEl = document.getElementById(`dp-step-${stepId}-detail`);
  if (detailEl) detailEl.textContent = detail || STEPS[i].defaultDetail;
}

function renderError(message) {
  const { processError, processStatus, cancelBtn, doneView, stepsContainer } = els();
  running = false;
  confirming = false;
  if (doneView) doneView.hidden = true;
  if (stepsContainer) stepsContainer.hidden = false;
  if (processError) {
    processError.hidden = false;
    processError.textContent = message;
  }
  if (processStatus) processStatus.textContent = 'Processing Failed';
  if (cancelBtn) cancelBtn.hidden = false;
}

function showConfirmationView() {
  const { stepsContainer, doneView, processFill, processStatus, cancelBtn } = els();
  running = false;
  confirming = true;
  if (stepsContainer) stepsContainer.hidden = true;
  if (doneView) doneView.hidden = false;
  if (processFill) processFill.style.width = '100%';
  if (processStatus) processStatus.textContent = 'Processing Done! ✓';
  if (cancelBtn) cancelBtn.hidden = true;
}

/**
 * Reveal the success state only after the final processing step really
 * reached 'completed'. Called from the last step's event; re-checks the
 * stage model rather than assuming completion.
 */
function completeUpload(file) {
  if (aborted) return;
  if (confirming) return;
  if (!file) return;
  if (stageStates[stageStates.length - 1] !== 'done') return;
  showConfirmationView();

  // Hold the confirmation ~1.2s, then close the modal and update the
  // trigger button label with the now-active custom dataset.
  window.setTimeout(() => {
    if (aborted) return;
    setDatasetSelection({ mode: 'custom', filename: file.name });
    onDatasetChange('custom', file.name);
    closeModal('dataset-modal');
    showPickerView();
  }, 1200);
}

function handleCloseDuringProcessing() {
  if (!running) return;
  aborted = true;
  running = false;
  showPickerView();
}

async function startUpload(file) {
  showProcessingView(file.name);
  try {
    const result = await processCustomDataset(file, file.name, (event) => {
      if (aborted) return;
      if (event.progress) {
        const fill = els().processFill;
        if (fill) fill.style.width = `${event.progress}%`;
      }
      if (event.step) {
        elStep(event.step, event.status, event.detail);
        // The done image is only shown once the FINAL processing step has
        // actually completed — never when an earlier step finishes.
        if (event.status === 'completed' && event.step === STEPS[STEPS.length - 1].id) {
          completeUpload(file);
        }
      }
    });

    if (aborted) return;

    // Safety net: if the pipeline resolved without the last step's event
    // reaching us, still require the last stage to be done before showing
    // the success state.
    if (!confirming) completeUpload(file);

    return result;
  } catch (err) {
    console.error('Custom ingestion error:', err);
    renderError(`Upload failed: ${err && err.message ? err.message : 'unknown error'}`);
    throw err;
  }
}

let onDatasetChange = () => {};

export function initDatasetPicker({ onDatasetChange: onChange }) {
  onDatasetChange = onChange || (() => {});

  const { btn, modal, fileInput, closeBtn, cancelBtn } = els();
  const label = els().label;

  renderDatasetTriggerLabel();
  onDatasetSelectionChange(() => {
    renderDatasetTriggerLabel();
  });

  if (btn) {
    // Hover affordance: blink back to the neutral "Choose Dataset" state.
    btn.addEventListener('mouseenter', () => {
      btn.classList.add('hovering');
      if (label) label.textContent = 'Choose Dataset';
    });
    btn.addEventListener('mouseleave', () => {
      btn.classList.remove('hovering');
      renderDatasetTriggerLabel();
    });
    btn.addEventListener('click', () => {
      btn.classList.remove('hovering');
      showPickerView();
      openModal('dataset-modal');
    });
  }

  const select = (mode) => {
    if (State.activeDatasetMode === mode) {
      setDatasetSelection({ mode, filename: null });
      closeModal('dataset-modal');
      return;
    }
    setDatasetSelection({ mode, filename: null });
    onDatasetChange(mode, null);
    closeModal('dataset-modal');
  };

  document.getElementById('dataset-opt-synthetic')?.addEventListener('click', () => select('synthetic'));
  document.getElementById('dataset-opt-hybrid')?.addEventListener('click', () => select('hybrid'));
  document.getElementById('dataset-upload-primary')?.addEventListener('click', () => fileInput?.click());

  cancelBtn?.addEventListener('click', () => {
    handleCloseDuringProcessing();
    closeModal('dataset-modal');
  });
  closeBtn?.addEventListener('click', () => {
    handleCloseDuringProcessing();
  });

  if (modal) {
    modal.addEventListener('mousedown', (e) => {
      if (e.target === modal) handleCloseDuringProcessing();
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      handleCloseDuringProcessing();
    }
  });

  fileInput?.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    fileInput.value = '';
    startUpload(file).catch(() => {});
  });
}