import { apiClient } from "~/lib/apiClient";
import type { User } from "~/types/user.types";

export const userService = {
  getMe(): Promise<User> {
    return apiClient.get<User>("/users/me");
  },
};
