import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { PageLoader } from './components/PageLoader';

// Heavy routes are code-split so the initial bundle stays lean — charts,
// markdown + highlight.js and the report document only load when visited.
const Landing = lazy(() => import('./pages/Landing'));
const RiskDashboard = lazy(() => import('./pages/RiskDashboard'));
const Consultant = lazy(() => import('./pages/Consultant'));
const InsuranceOptimiser = lazy(() => import('./pages/InsuranceOptimiser'));
const Assess = lazy(() => import('./pages/Assess'));
const LossSimulation = lazy(() => import('./pages/LossSimulation'));
const Insurance = lazy(() => import('./pages/Insurance'));
const Controls = lazy(() => import('./pages/Controls'));
const Methodology = lazy(() => import('./pages/Methodology'));
const Report = lazy(() => import('./pages/Report'));
const Settings = lazy(() => import('./pages/Settings'));

function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        {/* Public marketing landing page */}
        <Route index element={<Landing />} />

        {/* Consulting workspace */}
        <Route path="/app" element={<Layout />}>
          <Route index element={<RiskDashboard />} />
          <Route path="consult" element={<Consultant />} />
          <Route path="assess" element={<Assess />} />
          <Route path="simulate" element={<LossSimulation />} />
          <Route path="insurance" element={<Insurance />} />
          <Route path="optimise" element={<InsuranceOptimiser />} />
          <Route path="controls" element={<Controls />} />
          <Route path="methodology" element={<Methodology />} />
          <Route path="report" element={<Report />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default App;
