import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import "@fontsource-variable/manrope";
import "./styles/command-center.css";

createRoot(document.getElementById("cc-root")).render(
  <React.StrictMode>
    <ErrorBoundary where="the app">
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
