import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { PageLoader } from './components/PageLoader';

// Heavy routes are code-split so the initial bundle stays lean.
const Landing = lazy(() => import('./pages/Landing'));
const HowItWorks = lazy(() => import('./pages/HowItWorks'));
const ConsultantPortal = lazy(() => import('./pages/ConsultantPortal'));

function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route index element={<Landing />} />
        <Route path="/model" element={<HowItWorks />} />
        <Route path="/consult" element={<ConsultantPortal />} />
      </Routes>
    </Suspense>
  );
}

export default App;
