import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import "./index.css";

// 数据路由提供 useBlocker，设置草稿可以拦截站内导航和浏览器后退。
const router = createBrowserRouter([{ path: "*", element: <App /> }], {
  basename: import.meta.env.PROD ? "/admin" : undefined,
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
    <Toaster richColors position="top-right" />
  </StrictMode>,
);
