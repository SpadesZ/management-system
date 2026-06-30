// File Path: frontend/src/api/http.ts
// Timestamp: 2026-05-25T12:00:00+08:00
// Version: v0.1

import axios from "axios";

const http = axios.create({
  baseURL: "http://localhost:18001",
  timeout: 30000,
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      localStorage.removeItem("access_token");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export default http;
