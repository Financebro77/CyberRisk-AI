import { useEffect, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Fades a freshly-mounted page in.  Keyed by the current path so navigating
 * between routes re-triggers the entrance animation without a full remount
 * of the layout chrome.
 */
export function RouteTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [prevPath, setPrevPath] = useState(location.pathname);

  useEffect(() => {
    setPrevPath(location.pathname);
  }, [location.pathname]);

  // Use the path as a key so the animation plays per navigation.
  return (
    <div key={prevPath} className="panel-in">
      {children}
    </div>
  );
}
