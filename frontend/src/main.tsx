import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "@fontsource-variable/inter";
import "./styles.css";

declare global {
  interface Window {
    __appStarted?: boolean;
  }
}

// Tells the fallback in index.html that the app loaded fine.
window.__appStarted = true;

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
