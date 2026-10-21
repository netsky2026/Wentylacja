import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

axios.defaults.withCredentials = true;

let refreshing = null;
let onAuthLost = () => {};
export const setOnAuthLost = (fn) => { onAuthLost = fn; };

export const refreshSession = () => {
  if (!refreshing) refreshing = axios.post(`${API}/auth/refresh`).finally(() => { refreshing = null; });
  return refreshing;
};

axios.interceptors.response.use(undefined, async (error) => {
  const cfg = error.config;
  const url = cfg?.url || "";
  if (error.response?.status === 401 && !cfg._retry && !url.includes("/auth/")) {
    cfg._retry = true;
    try {
      await refreshSession();
      return axios(cfg);
    } catch (e) {
      onAuthLost();
    }
  }
  return Promise.reject(error);
});

export const formatApiError = (detail, fallback) => {
  if (detail == null) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (typeof detail.msg === "string") return detail.msg;
  return String(detail);
};

export const siteLogoUrl = (site, size) => site?.logo_version
  ? `${API}/public/site/logo?${size ? `size=${size}&` : ""}v=${site.logo_version}` : "/icon-192.png";
