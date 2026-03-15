import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./crt.css";

// Restore CRT scanline preference
if (localStorage.getItem("crt-scanlines") !== "off") {
  document.body.classList.add("crt-scanlines");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
