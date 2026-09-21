import { useMutation, useQueryClient } from "@tanstack/react-query";
import { authService } from "~/services/auth.service";
import { setToken } from "~/lib/auth";
import type { LoginInput } from "~/types/user.types";

export function useLogin() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: LoginInput) => authService.login(input),
    onSuccess: (data) => {
      setToken(data.token);
      queryClient.invalidateQueries({ queryKey: ["users", "me"] });
    },
  });
}
