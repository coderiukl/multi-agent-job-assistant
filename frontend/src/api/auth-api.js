import { requestJson } from "./http-client.js";

export async function registerAccount({ email, password }) {
  return requestJson(
    "/api/v1/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    },
    "Không thể kết nối với dịch vụ đăng ký.",
  );
}

export async function loginAccount({ email, password }) {
  const body = new URLSearchParams({
    grant_type: "password",
    username: email,
    password,
  });

  return requestJson(
    "/api/v1/auth/login",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    },
    "Không thể kết nối với dịch vụ đăng nhập.",
  );
}

export async function getCurrentUser() {
  const response = await requestJson(
    "/api/v1/auth/me",
    { method: "GET" },
    "Không thể xác minh phiên đăng nhập.",
  );

  return response?.data ?? response;
}
