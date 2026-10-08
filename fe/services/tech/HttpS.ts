import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";

import EnvS from "./EnvS";

// ============================================================================
// Private
// ============================================================================

const client: AxiosInstance = axios.create({
  baseURL: EnvS.apiUrl(),
  headers: { "Content-Type": "application/json" },
});

const withAuth = (token?: string | null, config?: AxiosRequestConfig): AxiosRequestConfig => {
  if (!token) return config ?? {};
  return {
    ...config,
    headers: { ...config?.headers, Authorization: `Bearer ${token}` },
  };
};

const get = async <T>(
  path: string,
  token?: string | null,
  config?: AxiosRequestConfig
): Promise<T> => {
  const res = await client.get<T>(path, withAuth(token, config));
  return res.data;
};

const post = async <T>(
  path: string,
  body?: unknown,
  token?: string | null,
  config?: AxiosRequestConfig
): Promise<T> => {
  const res = await client.post<T>(path, body, withAuth(token, config));
  return res.data;
};

const patch = async <T>(path: string, body?: unknown, token?: string | null): Promise<T> => {
  const res = await client.patch<T>(path, body, withAuth(token));
  return res.data;
};

const postForm = async <T>(path: string, formData: FormData, token?: string | null): Promise<T> => {
  const auth = withAuth(token);
  // Unset the instance-level Content-Type so the browser can set multipart/form-data with boundary
  const res = await client.post<T>(path, formData, {
    ...auth,
    headers: { ...auth.headers, "Content-Type": undefined },
  });
  return res.data;
};

// ============================================================================
// Public service API
// ============================================================================

const HttpS = { get, post, patch, postForm };
export default HttpS;
