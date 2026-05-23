import { useEffect, useState } from "react";
import { Bench } from "./pages/Bench";
import { Dashboard } from "./routes/Dashboard";

/**
 * Minimal path-based router. We don't pull in `react-router` because
 * Penumbra only has two top-level pages so far (dashboard + bench).
 * Listens to `popstate` so the browser back button works.
 */
export function App() {
  const [path, setPath] = useState<string>(() => window.location.pathname);

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  if (path.startsWith("/bench")) {
    return <Bench />;
  }
  return <Dashboard />;
}
