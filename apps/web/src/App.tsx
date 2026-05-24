import { useEffect, useState } from "react";
import { Bench } from "./pages/Bench";
import { Config } from "./pages/Config";
import { Operator } from "./pages/Operator";
import { Dashboard } from "./routes/Dashboard";

/**
 * Minimal path-based router. We don't pull in `react-router` because
 * Penumbra only has a handful of top-level pages (dashboard + bench
 * + operator + config). Listens to `popstate` so the browser back
 * button works.
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
  if (path.startsWith("/operator")) {
    return <Operator />;
  }
  if (path.startsWith("/config")) {
    return <Config />;
  }
  return <Dashboard />;
}
