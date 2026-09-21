import { apiClient } from "~/lib/apiClient";
import type { AuthResponse, LoginInput, RegisterInput } from "~/types/user.types";

export const authService = {
  register(input: RegisterInput): Promise<AuthResponse> {
    return apiClient.post<AuthResponse>("/auth/register", input);
  },

  login(input: LoginInput): Promise<AuthResponse> {
    return apiClient.post<AuthResponse>("/auth/login", input);
  },
};
