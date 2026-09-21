import { useQuery } from "@tanstack/react-query";
import { userService } from "~/services/user.service";
import { getToken } from "~/lib/auth";

export function useCurrentUser() {
  return useQuery({
    queryKey: ["users", "me"],
    queryFn: () => userService.getMe(),
    enabled: Boolean(getToken()),
  });
}
