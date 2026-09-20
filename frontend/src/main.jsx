import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles/command-center.css";

createRoot(document.getElementById("cc-root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
