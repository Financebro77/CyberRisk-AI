import '@testing-library/jest-dom/vitest';

// Recharts <ResponsiveContainer> needs ResizeObserver; happy-dom lacks it.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
