import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

function ScaffoldSmoke() {
  return <div className="p-6 text-foreground">DataVisSUS Agent</div>;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ScaffoldSmoke />
  </React.StrictMode>,
);
